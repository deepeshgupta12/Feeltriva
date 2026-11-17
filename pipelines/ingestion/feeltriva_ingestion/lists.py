"""Symptom text and symptom lists (M1.9), and the declared-count consistency checks.

Handoff rules applied here (`docs/04_DATA_MAPPING.md`):

- Archive 12 `symptom_text` and archive 14 `Symptoms` are comma-separated lists. They are parsed
  into terms; each distinct term becomes a list mapping (`feature_mappings` with no column
  position) to a lexical feature candidate, and each case gets one `case_features` row per
  listed term. Archive 12's text file is a separate representation: its rows are never
  aligned with `data.csv`.
- Term identity is lexical only (casefold, trim, collapse whitespace), the same rule as the
  matrix columns, so "shortness of breath" in a list and the column `shortness_of_breath` share
  one candidate. Terms that match nothing become new candidates. Everything stays `pending`.
- A listed term is stored as presence `present` with the wording as written. A term that is
  *not* listed gets no row: an unlisted symptom is unknown, never `absent`.
- `Symptom_Count` (archive 14) and `SYMPTOM_COUNT` (archive 15) are derived counts. They are
  compared with the parsed values as a data-quality check and a mismatch is flagged on the
  source record. They are not stored as features and are not ground truth.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import Engine, create_engine

from .archives import RAW_DIR, Manifest, load_manifest, read_csv_positional, verify_all
from .audit import norm_label
from .cases import _hash, _raw_cursor, case_files
from .features import _flush
from .load import RELEASE_ID, source_id

LIST_HEADERS = ("symptom_text", "symptoms")
COUNT_HEADER = "symptom_count"
COUNT_FLAG = "symptom_count_mismatch"
EMPTY_FLAG = "empty_symptom_list"


def feature_candidate_id(term: str) -> str:
    """Same deterministic ID the handoff audit gives a matrix column with this lexical term."""
    return "feat_" + hashlib.sha256(norm_label(term).encode()).hexdigest()[:16]


def list_mapping_id(sid: str, normalised_term: str) -> str:
    digest = hashlib.sha256("\x1f".join((RELEASE_ID, sid, "list", normalised_term)).encode()).hexdigest()
    return f"fm_{digest[:20]}"


def parse_list(text: str) -> list[str]:
    """Items of a comma-separated list, trimmed, in order, empty items dropped."""
    return [item for item in (part.strip() for part in text.split(",")) if item]


def list_files(manifest: Manifest) -> list[dict[str, Any]]:
    return [f for f in manifest.files if f.get("adapter") == "symptom_list"]


def _require_loaded(cur: Any, sid: str, label: str, expected_rows: int) -> None:
    # Row-level records only: a whole-file record (no row number) is provenance, not a row.
    cur.execute("SELECT count(*) FROM source_records WHERE source_id = %s AND row_number IS NOT NULL", (sid,))
    records = cur.fetchone()[0]
    if records != expected_rows:
        raise SystemExit(
            f"{label}: {records} rows loaded as records but {expected_rows} expected; run `load-cases` first"
        )


def _flag_rows(engine: Engine, sid: str, row_numbers: list[int], flag: str) -> int:
    """Add a quality flag to the given rows of one source. Re-running adds nothing."""
    if not row_numbers:
        return 0
    with _raw_cursor(engine) as cur:
        cur.execute(
            """UPDATE source_records SET quality_flags = quality_flags || %s::jsonb
               WHERE source_id = %s AND row_number = ANY(%s) AND NOT quality_flags @> %s::jsonb""",
            (json.dumps([flag]), sid, row_numbers, json.dumps([flag])),
        )
        return int(cur.rowcount)


def _load_list_file(
    engine: Engine, archive_path: Path, archive: str, file: str, expected_rows: int, batch_rows: int
) -> dict[str, Any]:
    sid = source_id(archive, file)
    label = f"{archive}/{file}"
    with _raw_cursor(engine) as cur:
        _require_loaded(cur, sid, label, expected_rows)
        cur.execute("SELECT 1 FROM mapping_releases WHERE release_id = %s", (RELEASE_ID,))
        if cur.fetchone() is None:
            raise SystemExit(f"mapping release {RELEASE_ID} does not exist; run `load` (reference data) first")

    # Pass 1: the vocabulary of this file. Small (hundreds of terms), so it is held in memory.
    terms: dict[str, str] = {}
    variants: dict[str, set[str]] = {}
    with zipfile.ZipFile(archive_path) as z:
        header, reader = read_csv_positional(z, file)
        lowered = [c.lower() for c in header]
        list_i = next(i for i, c in enumerate(lowered) if c in LIST_HEADERS)
        width = len(header)
        for cells in reader:
            if len(cells) != width:
                continue
            for item in parse_list(cells[list_i]):
                key = norm_label(item)
                terms.setdefault(key, item)
                variants.setdefault(key, set()).add(item)

    with _raw_cursor(engine) as cur:
        cur.execute(
            "SELECT feature_id FROM features WHERE feature_id = ANY(%s)", ([feature_candidate_id(t) for t in terms],)
        )
        existing = {row[0] for row in cur.fetchall()}
        new_features = 0
        for key in sorted(terms):
            feature_id = feature_candidate_id(key)
            if feature_id not in existing:
                # A term no matrix column has: a new lexical candidate, pending like all others.
                cur.execute(
                    """INSERT INTO features (feature_id, preferred_name, kind, value_type, aliases, status)
                       VALUES (%s, %s, 'other', 'boolean', %s::jsonb, 'pending') ON CONFLICT DO NOTHING""",
                    (feature_id, key, json.dumps(sorted(variants[key]))),
                )
                new_features += cur.rowcount
            cur.execute(
                """INSERT INTO feature_mappings (mapping_id, release_id, source_id, file_path, column_index,
                                                 original_term, feature_id, zero_semantics, transformation, status)
                   VALUES (%s, %s, %s, %s, NULL, %s, %s, 'unknown', %s::jsonb, 'pending') ON CONFLICT DO NOTHING""",
                (
                    list_mapping_id(sid, key),
                    RELEASE_ID,
                    sid,
                    file,
                    terms[key],
                    feature_id,
                    json.dumps(
                        {
                            "list_column": list_i,
                            "list_column_name": header[list_i],
                            "separator": ",",
                            "candidate_term": key,
                            "spellings": sorted(variants[key]),
                            "not_listed_means": "unknown",
                        }
                    ),
                ),
            )

    # Pass 2: one feature row per listed term per case.
    totals: dict[str, Any] = {
        "rows_read": 0,
        "items": 0,
        "distinct_terms": len(terms),
        "terms_reusing_existing_candidates": len(existing),
        "new_feature_candidates": new_features,
        "duplicate_items_in_a_row": 0,
        "empty_lists": 0,
        "rows_inserted": 0,
        "malformed_rows": 0,
        "declared_count_mismatches": None,
    }
    mapping_ids = {key: list_mapping_id(sid, key) for key in terms}
    mismatched: list[int] = []
    empty: list[int] = []
    with zipfile.ZipFile(archive_path) as z:
        header, reader = read_csv_positional(z, file)
        count_i = next((i for i, c in enumerate(c.lower() for c in header) if c == COUNT_HEADER), None)
        batch: list[tuple[Any, ...]] = []
        for n, cells in enumerate(reader, start=1):
            totals["rows_read"] += 1
            if len(cells) != width:
                totals["malformed_rows"] += 1
                continue
            items = parse_list(cells[list_i])
            totals["items"] += len(items)
            if not items:
                totals["empty_lists"] += 1
                empty.append(n)
            if count_i is not None and cells[count_i].strip() != str(len(items)):
                mismatched.append(n)
            case_id = f"case_{_hash(sid, str(n))}"
            seen: set[str] = set()
            for item in items:
                key = norm_label(item)
                if key in seen:  # the same term twice in one list is one fact, not two
                    totals["duplicate_items_in_a_row"] += 1
                    continue
                seen.add(key)
                batch.append((case_id, mapping_ids[key], item, "true", "present", False))
            if len(batch) >= batch_rows:
                totals["rows_inserted"] += _flush(engine, batch)
                batch = []
        if batch:
            totals["rows_inserted"] += _flush(engine, batch)
    if count_i is not None:
        totals["declared_count_mismatches"] = len(mismatched)
        totals["count_flags_added"] = _flag_rows(engine, sid, mismatched, COUNT_FLAG)
    totals["empty_flags_added"] = _flag_rows(engine, sid, empty, EMPTY_FLAG)
    return totals


def check_declared_counts(
    engine: Engine, archive_path: Path, archive: str, file: str, expected_rows: int
) -> dict[str, int] | None:
    """Matrix file with a declared symptom count (archive 15): compare it with the number of
    affirmed feature columns in the row. Returns None when the file has no such column."""
    sid = source_id(archive, file)
    with _raw_cursor(engine) as cur:
        _require_loaded(cur, sid, f"{archive}/{file}", expected_rows)
        cur.execute(
            "SELECT column_index FROM feature_mappings WHERE source_id = %s AND column_index IS NOT NULL", (sid,)
        )
        columns = sorted(int(r[0]) for r in cur.fetchall())
    mismatched: list[int] = []
    rows = 0
    with zipfile.ZipFile(archive_path) as z:
        header, reader = read_csv_positional(z, file)
        count_i = next((i for i, c in enumerate(c.lower() for c in header) if c == COUNT_HEADER), None)
        if count_i is None:
            return None
        width = len(header)
        for n, cells in enumerate(reader, start=1):
            if len(cells) != width:
                continue
            rows += 1
            affirmed = sum(1 for i in columns if cells[i] == "1")
            if cells[count_i].strip() != str(affirmed):
                mismatched.append(n)
    return {
        "rows_checked": rows,
        "feature_columns": len(columns),
        "declared_count_mismatches": len(mismatched),
        "count_flags_added": _flag_rows(engine, sid, mismatched, COUNT_FLAG),
    }


def summarise(cur: Any, sid: str) -> dict[str, int]:
    cur.execute(
        """SELECT count(*), count(DISTINCT cf.mapping_id), count(DISTINCT cf.case_id),
                  count(*) FILTER (WHERE cf.presence = 'present'), count(*) FILTER (WHERE cf.presence = 'absent')
           FROM case_features cf JOIN feature_mappings fm USING (mapping_id)
           WHERE fm.source_id = %s AND fm.column_index IS NULL""",
        (sid,),
    )
    keys = ("rows", "terms_used", "cases_with_items", "present_rows", "absent_rows")
    summary = dict(zip(keys, cur.fetchone(), strict=True))
    cur.execute("SELECT count(*) FROM feature_mappings WHERE source_id = %s AND column_index IS NULL", (sid,))
    summary["list_mappings"] = cur.fetchone()[0]
    return summary


def load_symptom_lists(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    only: set[str] | None = None,
    batch_rows: int = 250_000,
) -> dict[str, Any]:
    """Parse and load every symptom-list file, then check every declared symptom count."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)
    engine = create_engine(database_url)
    result: dict[str, Any] = {"files": {}, "summary": {}, "matrix_counts": {}}
    lists = [f for f in list_files(manifest) if only is None or f["file"] in only]
    for entry in lists:
        key = f"{entry['archive']}/{entry['file']}"
        result["files"][key] = _load_list_file(
            engine, raw_dir / entry["archive"], entry["archive"], entry["file"], entry["expected_rows"], batch_rows
        )
    for entry in case_files(manifest):
        if entry.get("adapter") != "positional_feature_matrix" or (only is not None and entry["file"] not in only):
            continue
        counts = check_declared_counts(
            engine, raw_dir / entry["archive"], entry["archive"], entry["file"], entry["expected_rows"]
        )
        if counts is not None:
            result["matrix_counts"][f"{entry['archive']}/{entry['file']}"] = counts
    with _raw_cursor(engine) as cur:
        for entry in lists:
            key = f"{entry['archive']}/{entry['file']}"
            result["summary"][key] = summarise(cur, source_id(entry["archive"], entry["file"]))
    engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Differences between what the list files contain and what is stored. Empty = consistent."""
    diffs = []
    for key, counts in result["files"].items():
        stored = result["summary"][key]
        expected = counts["items"] - counts["duplicate_items_in_a_row"]
        if stored["rows"] != expected:
            diffs.append(f"{key}: {stored['rows']} rows stored, {expected} distinct items per case in the file")
        if stored["list_mappings"] != counts["distinct_terms"]:
            diffs.append(f"{key}: {stored['list_mappings']} list mappings, {counts['distinct_terms']} distinct terms")
        if stored["absent_rows"] != 0:
            diffs.append(f"{key}: {stored['absent_rows']} rows marked absent; an unlisted symptom is never a denial")
    return diffs
