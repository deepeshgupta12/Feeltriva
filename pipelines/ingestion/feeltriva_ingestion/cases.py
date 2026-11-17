"""Row-level load of the case files (M1.7): source records, imported cases and their labels.

Every row of every matrix / symptom-list file becomes one immutable `source_records` row
(file + row locator + exact-content hash) and one `dataset_cases` row with its source-scoped
patient ID, original split, demographics as supplied, and a feature-profile cluster ID.
Rows are never merged or deleted: duplicates and repeated profiles are *flagged*.

Meaning of the derived fields (measured facts about files, not about people):

- content_hash: hash of all cells of the row. Equal hashes in one file = exact duplicate rows.
- profile_cluster_id: hash of all cells except the patient ID and the disease label, scoped to
  the archive and column layout. Equal IDs = the same feature profile; members may still carry
  different labels (kept as ambiguity) and may be different people. Cluster members must stay
  in the same split when ML data is partitioned.
- quality flag `profile_shared_across_original_split`: the profile occurs in more than one
  original split of the same archive (archive 15 train/test) - a leakage warning.

Cell-level feature values (`case_features`) are not loaded here; see docs/DECISIONS.md E23.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import Engine, create_engine

from .archives import RAW_DIR, Manifest, load_manifest, read_csv_positional, require_layouts, verify_all
from .audit import DISEASE_HEADERS, norm_label
from .load import disease_candidate_id, source_id

SPLIT_FLAG = "profile_shared_across_original_split"
_TMP_COLUMNS = (
    "row_number",
    "record_id",
    "content_hash",
    "flags",
    "malformed",
    "case_id",
    "source_patient_id",
    "age_value",
    "demo_field",
    "demo_value",
    "profile_cluster_id",
    "original_label",
    "norm_label",
    "disease_id",
)


def _hash(*parts: str) -> str:
    return hashlib.blake2b("\x1f".join(parts).encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


def case_files(manifest: Manifest) -> list[dict[str, Any]]:
    return [f for f in manifest.files if "dataset_cases" in f["targets"]]


def original_split(archive: str, file: str, manifest: Manifest) -> str | None:
    """A file is a split only when its archive ships several case files with the same layout
    name pattern (archive 15: train.csv / test.csv). The value is namespaced by archive."""
    stem = PurePosixPath(file).stem.lower()
    siblings = [f["file"] for f in case_files(manifest) if f["archive"] == archive]
    if stem in ("train", "test", "validation", "val") and len(siblings) > 1:
        return f"{archive}:{stem}"
    return None


def _age(raw: str) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 and value == value and value != float("inf") else None


@contextmanager
def _raw_cursor(engine: Engine) -> Iterator[Any]:
    """A psycopg cursor inside one transaction (COPY needs the driver-level cursor)."""
    with engine.begin() as conn:
        dbapi: Any = conn.connection.dbapi_connection
        cursor = dbapi.cursor()
        try:
            yield cursor
        finally:
            cursor.close()


_INSERTS = (
    # Labels absent from the reviewed crosswalk still get a provisional, pending lexical candidate.
    (
        "diseases",
        """INSERT INTO diseases (disease_id, preferred_name, status)
        SELECT DISTINCT ON (disease_id) disease_id, norm_label, 'pending' FROM tmp_cases WHERE NOT malformed
        ON CONFLICT DO NOTHING""",
        (),
    ),
    (
        "records",
        """INSERT INTO source_records (record_id, source_id, file_path, row_number, content_hash,
                                              raw_object_uri, original_split, quality_flags)
        SELECT record_id, %s, %s, row_number, content_hash, %s || row_number, %s, flags::jsonb FROM tmp_cases
        ON CONFLICT DO NOTHING""",
        ("sid", "file", "uri", "split"),
    ),
    (
        "cases",
        """INSERT INTO dataset_cases (case_id, record_id, source_patient_id, source_split, age_value,
                     original_demographic_field, original_demographic_value, profile_cluster_id)
        SELECT case_id, record_id, source_patient_id, %s, age_value, demo_field, demo_value, profile_cluster_id
        FROM tmp_cases WHERE NOT malformed
        ON CONFLICT DO NOTHING""",
        ("split",),
    ),
    (
        "labels",
        """INSERT INTO case_labels (case_id, disease_id, original_label, label_origin)
        SELECT case_id, disease_id, original_label, 'unknown' FROM tmp_cases WHERE NOT malformed
        ON CONFLICT DO NOTHING""",
        (),
    ),
)


def _flush(engine: Engine, batch: list[tuple[Any, ...]], params: dict[str, Any]) -> dict[str, int]:
    """Write one batch in its own transaction: COPY into a temp table, then idempotent inserts."""
    counts = {}
    with _raw_cursor(engine) as cur:
        cur.execute(
            """CREATE TEMP TABLE tmp_cases (
                row_number bigint, record_id text, content_hash text, flags text, malformed boolean, case_id text,
                source_patient_id text, age_value numeric, demo_field text, demo_value text,
                profile_cluster_id text, original_label text, norm_label text, disease_id text
            ) ON COMMIT DROP"""
        )
        with cur.copy(f"COPY tmp_cases ({', '.join(_TMP_COLUMNS)}) FROM STDIN") as copy:
            for row in batch:
                copy.write_row(row)
        for name, statement, names in _INSERTS:
            cur.execute(statement, tuple(params[n] for n in names))
            counts[name] = cur.rowcount
    return counts


def _load_file(
    engine: Engine, archive_path: Path, archive: str, file: str, split: str | None, batch_rows: int = 20_000
) -> dict[str, int]:
    """Stream one case file into the database in bounded batches. Each batch commits on its own,
    so no transaction grows with file size and an interrupted load resumes on rerun."""
    sid = source_id(archive, file)
    with _raw_cursor(engine) as cur:
        cur.execute("SELECT 1 FROM sources WHERE source_id = %s", (sid,))
        if cur.fetchone() is None:
            raise SystemExit(f"source for {archive}/{file} is not registered; run `load` (reference data) first")
    params = {"sid": sid, "file": file, "uri": f"zip://{archive}#{file}:row=", "split": split}
    totals = {"rows_read": 0, "records_inserted": 0, "cases_inserted": 0, "labels_inserted": 0, "batches": 0}

    def flush(batch: list[tuple[Any, ...]]) -> None:
        counts = _flush(engine, batch, params)
        totals["records_inserted"] += counts["records"]
        totals["cases_inserted"] += counts["cases"]
        totals["labels_inserted"] += counts["labels"]
        totals["batches"] += 1

    with zipfile.ZipFile(archive_path) as z:
        header, reader = read_csv_positional(z, file)
        lowered = [c.lower() for c in header]
        width = len(header)
        label_i = next(i for i, c in enumerate(lowered) if c in DISEASE_HEADERS)
        id_i = next((i for i, c in enumerate(lowered) if c == "patient_id"), None)
        age_i = next((i for i, c in enumerate(lowered) if c == "age"), None)
        demo_i = next((i for i, c in enumerate(lowered) if c in ("sex", "gender")), None)
        excluded = {label_i} | ({id_i} if id_i is not None else set())
        # Same archive + same column layout (ignoring the ID column) = comparable profiles.
        namespace = _hash(archive, *[c for i, c in enumerate(header) if i != id_i])
        batch: list[tuple[Any, ...]] = []
        for n, cells in enumerate(reader, start=1):
            totals["rows_read"] += 1
            record_id = f"rec_{_hash(sid, str(n))}"
            content = _hash(*cells)
            if len(cells) != width:
                batch.append(
                    (
                        n,
                        record_id,
                        content,
                        '["malformed_row"]',
                        True,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                )
            else:
                flags = []
                age = None
                if age_i is not None:
                    age = _age(cells[age_i])
                    if age is None:
                        flags.append("age_not_parsed")
                label = cells[label_i]
                batch.append(
                    (
                        n,
                        record_id,
                        content,
                        json.dumps(flags),
                        False,
                        f"case_{_hash(sid, str(n))}",
                        cells[id_i] if id_i is not None else None,
                        age,
                        header[demo_i] if demo_i is not None else None,
                        cells[demo_i] if demo_i is not None else None,
                        f"pc_{_hash(namespace, *[c for i, c in enumerate(cells) if i not in excluded])}",
                        label,
                        norm_label(label),
                        disease_candidate_id(label),
                    )
                )
            if len(batch) >= batch_rows:
                flush(batch)
                batch = []
        if batch:
            flush(batch)
    return totals


def _finalise(cur: Any, source_ids: list[str]) -> dict[str, int]:
    """Derive duplicate status and the cross-split flag. Re-running changes nothing."""
    cur.execute(
        """WITH counted AS (
               SELECT c.case_id,
                      count(*) OVER (PARTITION BY r.source_id, r.content_hash) AS exact_n,
                      count(*) OVER (PARTITION BY c.profile_cluster_id) AS cluster_n
               FROM dataset_cases c JOIN source_records r USING (record_id)
               WHERE r.source_id = ANY(%s)),
           derived AS (
               SELECT case_id, CASE WHEN exact_n > 1 THEN 'exact_duplicate_row'
                                    WHEN cluster_n > 1 THEN 'repeated_profile'
                                    ELSE 'no_duplicate_detected' END AS status
               FROM counted)
           UPDATE dataset_cases c SET duplicate_status = d.status
           FROM derived d WHERE c.case_id = d.case_id AND c.duplicate_status IS DISTINCT FROM d.status""",
        (source_ids,),
    )
    statuses = cur.rowcount
    cur.execute(
        """WITH shared AS (
               SELECT c.profile_cluster_id
               FROM dataset_cases c JOIN source_records r USING (record_id)
               WHERE r.source_id = ANY(%s) AND c.source_split IS NOT NULL
               GROUP BY c.profile_cluster_id HAVING count(DISTINCT c.source_split) > 1)
           UPDATE source_records r SET quality_flags = r.quality_flags || %s::jsonb
           FROM dataset_cases c JOIN shared USING (profile_cluster_id)
           WHERE c.record_id = r.record_id AND r.source_id = ANY(%s) AND NOT r.quality_flags @> %s::jsonb""",
        (source_ids, json.dumps([SPLIT_FLAG]), source_ids, json.dumps([SPLIT_FLAG])),
    )
    return {"duplicate_status_updates": statuses, "split_overlap_flags_added": cur.rowcount}


def summarise(cur: Any, sid: str) -> dict[str, int]:
    cur.execute(
        """SELECT count(*), count(DISTINCT r.content_hash), count(c.case_id), count(DISTINCT c.profile_cluster_id),
                  count(*) FILTER (WHERE c.duplicate_status = 'exact_duplicate_row'),
                  count(*) FILTER (WHERE c.duplicate_status = 'repeated_profile'),
                  count(*) FILTER (WHERE r.quality_flags @> %s::jsonb),
                  count(*) FILTER (WHERE r.quality_flags @> '["malformed_row"]'::jsonb)
           FROM source_records r LEFT JOIN dataset_cases c USING (record_id)
           WHERE r.source_id = %s AND r.row_number IS NOT NULL""",
        (json.dumps([SPLIT_FLAG]), sid),
    )
    keys = (
        "records",
        "exact_unique_rows",
        "cases",
        "profile_clusters",
        "rows_in_exact_duplicate_groups",
        "rows_in_repeated_profiles",
        "rows_flagged_shared_across_split",
        "malformed_rows",
    )
    return dict(zip(keys, cur.fetchone(), strict=True))


def load_cases(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    only: set[str] | None = None,
    batch_rows: int = 20_000,
) -> dict[str, Any]:
    """Load every case file (or only the named files). Returns per-file load counts, the
    finalisation counts and a per-file summary read back from the database."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)
    targets = [f for f in case_files(manifest) if only is None or f["file"] in only]
    require_layouts(raw_dir, targets, (DISEASE_HEADERS,))  # a file whose columns changed is refused up front
    engine = create_engine(database_url)
    result: dict[str, Any] = {"files": {}, "summary": {}}
    for entry in targets:
        archive, file = entry["archive"], entry["file"]
        result["files"][f"{archive}/{file}"] = _load_file(
            engine, raw_dir / archive, archive, file, original_split(archive, file, manifest), batch_rows
        )
    source_ids = [source_id(f["archive"], f["file"]) for f in targets]
    with _raw_cursor(engine) as cur:
        result["finalise"] = _finalise(cur, source_ids)
        for entry in targets:
            key = f"{entry['archive']}/{entry['file']}"
            result["summary"][key] = summarise(cur, source_id(entry["archive"], entry["file"]))
    engine.dispose()
    return result


def compare_with_manifest(result: dict[str, Any], manifest: Manifest | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    expected = {f"{f['archive']}/{f['file']}": f for f in case_files(manifest)}
    diffs = []
    for key, summary in result["summary"].items():
        want = expected[key]
        if summary["records"] != want["expected_rows"]:
            diffs.append(f"{key} records: {summary['records']} != manifest {want['expected_rows']}")
        if summary["exact_unique_rows"] != want["exact_unique_rows"]:
            diffs.append(
                f"{key} exact unique rows: {summary['exact_unique_rows']} != manifest {want['exact_unique_rows']}"
            )
        if summary["cases"] + summary["malformed_rows"] != summary["records"]:
            diffs.append(f"{key}: cases + malformed != records")
    return diffs
