"""Loads reviewable reference data into PostgreSQL. Everything arrives as `pending`:
lexical disease candidates, positional feature mappings and narrative statements are review
material, not approved clinical content. Loading is idempotent (ON CONFLICT DO NOTHING on
deterministic IDs), original labels and column positions are preserved, and nothing is merged.

Row-level matrix data (dataset_cases / case_features) is not loaded here: see plan item M1.7.
"""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from feeltriva_api.models import (
    Disease,
    DiseaseMapping,
    Feature,
    FeatureMapping,
    MappingRelease,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from feeltriva_api.settings import Settings
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from .archives import RAW_DIR, ROOT, load_manifest, read_csv_positional, verify_all
from .audit import REFERENCE_AUDIT, norm_label

AUDIT_DIR = ROOT / "data_audit"
RELEASE_ID = "mapping-lexical-0"
NARRATIVE = {
    "causes.csv": ("cause", "cause"),
    "symptoms.csv": ("symptom", "symptom"),
    "treatments.csv": ("treatment", "treatment"),
}


def _h(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def source_id(archive: str, file: str) -> str:
    return f"src_{_h(archive, file)[:16]}"


def disease_candidate_id(label: str) -> str:
    """Same deterministic ID the handoff audit assigned: hash of the normalised lexical label."""
    return "dis_" + hashlib.sha256(norm_label(label).encode()).hexdigest()[:16]


def _rows(name: str) -> list[dict[str, str]]:
    with (AUDIT_DIR / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _insert(conn: Connection, model: Any, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), 1000):
        conn.execute(insert(model).on_conflict_do_nothing(), rows[start : start + 1000])


def load_reference(raw_dir: Path = RAW_DIR, database_url: str | None = None) -> dict[str, tuple[int, int]]:
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = load_manifest()
    verify_all(raw_dir, manifest)
    reference = json.loads(REFERENCE_AUDIT.read_text(encoding="utf-8"))
    conflicts = {(f["archive"], f["file"]): f["duplicate_column_disagreement_rows"] for f in reference["files"]}
    models = [
        Source,
        MappingRelease,
        Disease,
        DiseaseMapping,
        Feature,
        FeatureMapping,
        SourceRecord,
        Statement,
        StatementSource,
    ]
    engine = create_engine(database_url)
    with engine.begin() as conn:
        before = {m.__tablename__: conn.execute(select(func.count()).select_from(m)).scalar_one() for m in models}

        # -- sources: one immutable version per file, tied to its archive digest ----------------
        sources: list[dict[str, Any]] = []
        archives: dict[str, zipfile.ZipFile] = {a: zipfile.ZipFile(raw_dir / a) for a in manifest.archives}
        try:
            for entry in manifest.files:
                archive, file = entry["archive"], entry["file"]
                sources.append(
                    {
                        "source_id": source_id(archive, file),
                        "source_name": f"{archive}/{file}",
                        "version": manifest.archives[archive][:16],
                        "sha256": hashlib.sha256(archives[archive].read(file)).hexdigest(),
                        "provenance_status": "pending",
                    }
                )
            text_archive = "archive(13).zip"
            text_source = source_id(text_archive, "*.txt")
            sources.append(
                {
                    "source_id": text_source,
                    "source_name": f"{text_archive}/*.txt",
                    "version": manifest.archives[text_archive][:16],
                    "sha256": manifest.archives[text_archive],
                    "provenance_status": "pending",
                }
            )
            _insert(conn, Source, sources)
            _insert(conn, MappingRelease, [{"release_id": RELEASE_ID, "version": "lexical-0", "status": "pending"}])

            # -- lexical disease candidates and their source labels ------------------------------
            _insert(
                conn,
                Disease,
                [
                    {"disease_id": r["candidate_id"], "preferred_name": r["lexical_term"], "status": "pending"}
                    for r in _rows("disease_candidate_catalog.csv")
                ],
            )
            native_ids: dict[str, str] = {}
            header, rows = read_csv_positional(archives["archive(13).zip"], "diseases_main.csv")
            main_rows = [dict(zip(header, row, strict=True)) for row in rows]
            for row in main_rows:
                native_ids[row["name"]] = row["id"]
            mappings: dict[str, dict[str, Any]] = {}
            for r in _rows("disease_mappings.csv"):
                sid = source_id(r["archive"], r["file"])
                mapping_id = f"dm_{_h(RELEASE_ID, sid, r['source_label'])[:20]}"
                mappings[mapping_id] = {
                    "mapping_id": mapping_id,
                    "release_id": RELEASE_ID,
                    "source_id": sid,
                    "original_label": r["source_label"],
                    "disease_id": r["candidate_disease_id"],
                    "original_id": native_ids.get(r["source_label"]) if r["archive"] == "archive(13).zip" else None,
                    "method": "lexical_casefold_whitespace",
                    "status": "pending",
                }
            _insert(conn, DiseaseMapping, list(mappings.values()))

            # -- lexical feature candidates and positional column mappings -----------------------
            _insert(
                conn,
                Feature,
                [
                    {
                        "feature_id": r["candidate_id"],
                        "preferred_name": r["lexical_term"],
                        "kind": "other",
                        "value_type": "boolean",
                        "aliases": json.loads(r["original_terms_json"]),
                        "status": "pending",
                    }
                    for r in _rows("feature_candidate_catalog.csv")
                ],
            )
            column_rows = _rows("feature_column_mappings.csv")
            positions: dict[tuple[str, str, str], list[int]] = {}
            for r in column_rows:
                positions.setdefault((r["archive"], r["file"], r["original_header"]), []).append(int(r["column_index"]))
            feature_mappings = []
            for r in column_rows:
                sid = source_id(r["archive"], r["file"])
                same_name = positions[(r["archive"], r["file"], r["original_header"])]
                transformation: dict[str, Any] = {
                    "audit_status": r["mapping_status"],
                    "candidate_term": r["candidate_term"],
                }
                if len(same_name) > 1:  # repeated header: keep each position, record the measured conflict
                    transformation.update(
                        repeated_header=True,
                        repeated_positions=same_name,
                        disagreement_rows=conflicts[(r["archive"], r["file"])].get(r["original_header"], 0),
                    )
                feature_mappings.append(
                    {
                        "mapping_id": f"fm_{_h(RELEASE_ID, sid, r['column_index'])[:20]}",
                        "release_id": RELEASE_ID,
                        "source_id": sid,
                        "file_path": r["file"],
                        "column_index": int(r["column_index"]),
                        "original_term": r["original_header"],
                        "feature_id": r["candidate_feature_id"],
                        "zero_semantics": "unknown",
                        "transformation": transformation,
                        "status": "pending",
                    }
                )
            _insert(conn, FeatureMapping, feature_mappings)

            # -- narrative statements with provenance (archive 13 native FK, archive 16) ---------
            records: list[dict[str, Any]] = []
            statements: dict[str, dict[str, Any]] = {}
            links: dict[tuple[str, str], dict[str, Any]] = {}

            def add(
                archive: str,
                file: str,
                row_number: int,
                row: list[str],
                disease_label: str,
                statement_type: str,
                text: str,
                url: str | None,
                span: dict[str, Any],
                flags: list[str],
            ) -> None:
                sid = source_id(archive, file)
                record_id = f"rec_{_h(sid, row_number)[:24]}"
                records.append(
                    {
                        "record_id": record_id,
                        "source_id": sid,
                        "file_path": file,
                        "row_number": row_number,
                        "content_hash": _h(*row),
                        "raw_object_uri": f"zip://{archive}#{file}:row={row_number}",
                        "quality_flags": flags,
                    }
                )
                if not text.strip():
                    return
                disease_id = disease_candidate_id(disease_label)
                # Identical normalised text for the same disease/type/source is one statement
                # that keeps every attribution.
                statement_id = f"st_{_h(sid, disease_id, statement_type, norm_label(text))[:24]}"
                statements.setdefault(
                    statement_id,
                    {
                        "statement_id": statement_id,
                        "disease_id": disease_id,
                        "statement_type": statement_type,
                        "text_content": text,
                        "status": "pending",
                    },
                )
                links[(statement_id, record_id)] = {
                    "statement_id": statement_id,
                    "record_id": record_id,
                    "source_url": url or None,
                    "text_span": span,
                }

            a13 = "archive(13).zip"
            by_native = {row["id"]: row for row in main_rows}
            for n, row in enumerate(main_rows, start=1):
                add(
                    a13,
                    "diseases_main.csv",
                    n,
                    list(row.values()),
                    row["name"],
                    "description",
                    row["summary"],
                    row["url"],
                    {"column": "summary", "native_id": row["id"], "source_category": row["category"]},
                    [],
                )
            for file, (statement_type, column) in NARRATIVE.items():
                header, rows = read_csv_positional(archives[a13], file)
                for n, cells in enumerate(rows, start=1):
                    row = dict(zip(header, cells, strict=True))
                    main = by_native.get(row["disease_id"])
                    flags = []
                    if main is None:
                        flags.append("unknown_native_disease_id")
                    elif norm_label(main["name"]) != norm_label(row["disease_name"]):
                        flags.append("disease_name_disagrees_with_diseases_main")
                    add(
                        a13,
                        file,
                        n,
                        cells,
                        main["name"] if main else row["disease_name"],
                        statement_type,
                        row[column],
                        main["url"] if main else None,
                        {"column": column, "native_id": row["disease_id"]},
                        flags,
                    )
            a16, f16 = "archive(16).zip", "symptom_Description_820_verified_v5.csv"
            header, rows = read_csv_positional(archives[a16], f16)
            for n, cells in enumerate(rows, start=1):
                row = dict(zip(header, cells, strict=True))
                add(
                    a16,
                    f16,
                    n,
                    cells,
                    row["Disease"],
                    "description",
                    row["Description"],
                    row["Source_URL"],
                    {
                        "column": "Description",
                        "source": row["Source"],
                        "retrieved_date": row["Retrieved_Date"],
                        "canonical_query": row["Canonical_Query"],
                    },
                    [],
                )
            for text in manifest.text_files:  # narrative files: registered, not yet split into statements
                records.append(
                    {
                        "record_id": f"rec_{_h(text_source, text['file'])[:24]}",
                        "source_id": text_source,
                        "file_path": text["file"],
                        "row_number": None,
                        "content_hash": text["sha256"],
                        "raw_object_uri": f"zip://{text['archive']}#{text['file']}",
                        "quality_flags": [],
                    }
                )
            _insert(conn, SourceRecord, records)
            _insert(conn, Statement, list(statements.values()))
            _insert(conn, StatementSource, list(links.values()))
        finally:
            for archive_file in archives.values():
                archive_file.close()
        after = {m.__tablename__: conn.execute(select(func.count()).select_from(m)).scalar_one() for m in models}
    return {table: (after[table] - before[table], after[table]) for table in after}
