"""Cell-level feature values of the matrix files (M1.8): `case_features`.

Handoff rules applied here:

- "A blank matrix value, an imported zero and an explicit denial are different concepts."
  A `0` is therefore never stored as a row and never as `absent`. For a registered column of a
  case's file, the absence of a row means the source cell was `0`; what that zero means stays
  on the mapping (`feature_mappings.zero_semantics = 'unknown'`) until a reviewer decides.
- Every other cell is stored with its raw value:
    `1`      -> presence `present`   (the source row affirms this column)
    blank    -> presence `not_asked` (no value recorded; not a zero)
    other    -> presence `uncertain` (kept verbatim, needs review)
- Repeated header names (archive 16): each column position keeps its own row. Where the
  positions of one header disagree for a case, *all* positions of that header are stored for
  that case, zeros included, with `conflict = true` and presence `uncertain`. Contradictory
  values are never OR-ed into one.
- Columns are addressed by position. If a header no longer matches the registered mapping the
  load stops (source schema drift).

`presence = 'present'` says only that the source affirms the column. Whether the column is a
symptom, a history item or a risk factor is a property of the feature and is still unreviewed
(plan item M2.7); nothing here may be read as an approved clinical fact.
"""

from __future__ import annotations

import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import Engine, create_engine

from .archives import RAW_DIR, Manifest, load_manifest, read_csv_positional, verify_all
from .cases import _hash, _raw_cursor
from .load import source_id

_COLUMNS = ("case_id", "mapping_id", "raw_value", "normalized", "presence", "conflict")


def matrix_files(manifest: Manifest) -> list[dict[str, Any]]:
    return [f for f in manifest.files if f.get("adapter") == "positional_feature_matrix"]


def _classify(raw: str) -> tuple[str | None, str]:
    """(normalized JSON text, presence) for a stored cell."""
    if raw == "1":
        return "true", "present"
    if raw == "":
        return None, "not_asked"
    if raw == "0":  # only reached for the zero side of a conflicting repeated header
        return "false", "uncertain"
    return None, "uncertain"


def _flush(engine: Engine, batch: list[tuple[Any, ...]]) -> int:
    with _raw_cursor(engine) as cur:
        cur.execute(
            """CREATE TEMP TABLE tmp_features (
                case_id text, mapping_id text, raw_value text, normalized text, presence text, conflict boolean
            ) ON COMMIT DROP"""
        )
        with cur.copy(f"COPY tmp_features ({', '.join(_COLUMNS)}) FROM STDIN") as copy:
            for row in batch:
                copy.write_row(row)
        cur.execute(
            """INSERT INTO case_features (case_id, mapping_id, raw_value, normalized_value, presence, conflict)
               SELECT case_id, mapping_id, raw_value, normalized::jsonb, presence::presence_state, conflict
               FROM tmp_features
               ON CONFLICT DO NOTHING"""
        )
        return int(cur.rowcount)


def _load_file(
    engine: Engine, archive_path: Path, archive: str, file: str, expected_rows: int, batch_rows: int
) -> dict[str, int]:
    sid = source_id(archive, file)
    with _raw_cursor(engine) as cur:
        cur.execute(
            "SELECT column_index, mapping_id, original_term FROM feature_mappings "
            "WHERE source_id = %s AND column_index IS NOT NULL",
            (sid,),
        )
        mappings = {int(i): (mapping_id, term) for i, mapping_id, term in cur.fetchall()}
        # Every row of the file is a source record; a malformed row is a record without a case.
        cur.execute("SELECT count(*) FROM source_records WHERE source_id = %s", (sid,))
        records = cur.fetchone()[0]
    if not mappings:
        raise SystemExit(f"no column mappings for {archive}/{file}; run `load` (reference data) first")
    if records != expected_rows:
        raise SystemExit(
            f"{archive}/{file}: {records} rows loaded as records but {expected_rows} expected; run `load-cases` first"
        )
    totals = {
        "rows_read": 0,
        "feature_columns": len(mappings),
        "non_zero_cells": 0,
        "blank_cells": 0,
        "other_value_cells": 0,
        "conflict_groups": 0,
        "rows_inserted": 0,
        "malformed_rows": 0,
    }
    with zipfile.ZipFile(archive_path) as z:
        header, reader = read_csv_positional(z, file)
        for index, (_, term) in mappings.items():
            if index >= len(header) or header[index] != term:
                found = header[index] if index < len(header) else None
                raise SystemExit(
                    f"{archive}/{file}: column {index} is {found!r} but the registered mapping says {term!r} "
                    "(source schema drift); nothing was loaded"
                )
        columns = sorted(mappings)
        ids = {i: mappings[i][0] for i in columns}
        repeated = [
            positions
            for positions in (
                [i for i in columns if header[i] == name]
                for name, n in Counter(header[i] for i in columns).items()
                if n > 1
            )
        ]
        width = len(header)
        batch: list[tuple[Any, ...]] = []
        for n, cells in enumerate(reader, start=1):
            totals["rows_read"] += 1
            if len(cells) != width:
                totals["malformed_rows"] += 1
                continue
            case_id = f"case_{_hash(sid, str(n))}"
            conflicted: set[int] = set()
            for positions in repeated:
                first = cells[positions[0]]
                if any(cells[i] != first for i in positions[1:]):
                    conflicted.update(positions)
                    totals["conflict_groups"] += 1
            for i in columns:
                raw = cells[i]
                if i in conflicted:  # explicit conflict: keep every position, zero included
                    normalized, _ = _classify(raw)
                    batch.append((case_id, ids[i], raw, normalized, "uncertain", True))
                    if raw != "0":
                        totals["non_zero_cells"] += 1
                    continue
                if raw == "0":
                    continue
                totals["non_zero_cells"] += 1
                normalized, presence = _classify(raw)
                if raw == "":
                    totals["blank_cells"] += 1
                elif raw != "1":
                    totals["other_value_cells"] += 1
                batch.append((case_id, ids[i], raw, normalized, presence, False))
            if len(batch) >= batch_rows:
                totals["rows_inserted"] += _flush(engine, batch)
                batch = []
        if batch:
            totals["rows_inserted"] += _flush(engine, batch)
    return totals


def summarise(cur: Any, sid: str) -> dict[str, Any]:
    """Read back what is stored for one source file."""
    cur.execute(
        """SELECT count(*), count(*) FILTER (WHERE cf.raw_value <> '0'), count(*) FILTER (WHERE cf.conflict),
                  count(*) FILTER (WHERE cf.raw_value = '0'),
                  count(*) FILTER (WHERE cf.raw_value = '0' AND NOT cf.conflict),
                  count(*) FILTER (WHERE cf.presence = 'present'), count(*) FILTER (WHERE cf.presence = 'absent')
           FROM case_features cf JOIN feature_mappings fm USING (mapping_id) WHERE fm.source_id = %s""",
        (sid,),
    )
    keys = (
        "rows",
        "non_zero_rows",
        "conflict_rows",
        "zero_rows",
        "zero_rows_outside_conflicts",
        "present_rows",
        "absent_rows",
    )
    summary: dict[str, Any] = dict(zip(keys, cur.fetchone(), strict=True))
    cur.execute(
        """SELECT fm.original_term, count(DISTINCT cf.case_id)
           FROM case_features cf JOIN feature_mappings fm USING (mapping_id)
           WHERE fm.source_id = %s AND cf.conflict GROUP BY fm.original_term""",
        (sid,),
    )
    summary["conflict_cases_by_header"] = dict(cur.fetchall())
    return summary


def load_case_features(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    only: set[str] | None = None,
    batch_rows: int = 250_000,
) -> dict[str, Any]:
    """Load the feature values of every matrix file (or only the named files)."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)
    targets = [f for f in matrix_files(manifest) if only is None or f["file"] in only]
    engine = create_engine(database_url)
    result: dict[str, Any] = {"files": {}, "summary": {}}
    for entry in targets:
        key = f"{entry['archive']}/{entry['file']}"
        result["files"][key] = _load_file(
            engine, raw_dir / entry["archive"], entry["archive"], entry["file"], entry["expected_rows"], batch_rows
        )
    with _raw_cursor(engine) as cur:
        for entry in targets:
            key = f"{entry['archive']}/{entry['file']}"
            result["summary"][key] = summarise(cur, source_id(entry["archive"], entry["file"]))
    engine.dispose()
    return result


def check(result: dict[str, Any], audit_files: list[dict[str, Any]] | None = None) -> list[str]:
    """Differences between what the files contain, what is stored, and the handoff's measured
    repeated-header conflicts (`data_audit/audit.json`). Empty = consistent."""
    diffs = []
    expected_conflicts = {
        f"{f['archive']}/{f['file']}": f["duplicate_column_disagreement_rows"] for f in (audit_files or [])
    }
    for key, counts in result["files"].items():
        stored = result["summary"][key]
        if stored["non_zero_rows"] != counts["non_zero_cells"]:
            diffs.append(
                f"{key}: {stored['non_zero_rows']} non-zero rows stored, {counts['non_zero_cells']} in the file"
            )
        if stored["zero_rows_outside_conflicts"] != 0:
            diffs.append(f"{key}: {stored['zero_rows_outside_conflicts']} zero cells stored outside a conflict")
        if stored["absent_rows"] != 0:
            diffs.append(f"{key}: {stored['absent_rows']} rows marked absent; an imported zero is never a denial")
        if key in expected_conflicts and stored["conflict_cases_by_header"] != expected_conflicts[key]:
            diffs.append(f"{key}: repeated-header conflicts differ from data_audit/audit.json")
    return diffs
