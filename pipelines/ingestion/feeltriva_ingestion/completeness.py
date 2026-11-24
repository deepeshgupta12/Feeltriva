"""Ingestion completeness check (M1.13).

Walks every row of the source-to-target table in `docs/04_DATA_MAPPING.md` and puts the count
loaded in the database next to the count expected for that row. Expected values come from the
handoff (the manifest, `data_audit/audit.json`, the crosswalk files, numbers stated in the
mapping table itself) or from an independent recount of the source files (`verify_files`).

The check is read-only: it runs in a READ ONLY transaction and changes nothing. A row of the
mapping table that has no check is reported as a mismatch, so a requirement cannot be skipped
silently. Work that the table asks for but a later sub-step owns is listed as `later`, with
that sub-step named; it is never counted as done.

This says the data is loaded as the mapping table requires. It says nothing about clinical
validity. Every mapping, statement and evidence row checked here is `pending` or carries a
reviewer's recorded decision; a row whose status was changed by no reviewer is a mismatch
(`decisions.py`).
"""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import ADAPTER_COLUMNS, RAW_DIR, ROOT, Manifest, load_manifest, read_csv_positional, verify_all
from .audit import REFERENCE_AUDIT, norm_label
from .cases import _raw_cursor, original_split
from .chunks import CATEGORY_FLAG, KNOWLEDGE_RELEASE_ID, TEXT_ARCHIVE
from .completeness_rows import emit
from .decisions import IN_ORDER, changed_by_no_reviewer, standing
from .evidence import (
    _QUESTION_TERM,
    COOCCURRENCE_TYPE,
    MIN_TERM_LENGTH,
    NARRATIVE_TYPE,
    find_mentions,
    term_pattern,
    whole_file_record_id,
)
from .load import AUDIT_DIR, RELEASE_ID, source_id
from .objectstore import ObjectStoreSettings, _stored_digest, make_client
from .verify_files import role_positions, verify_case_file, verify_statement_file, verify_text_files

DOC = ROOT / "docs" / "04_DATA_MAPPING.md"
TABLE_HEADING = "## Source fields and exact target mapping"
OK, MISMATCH, LATER = "ok", "MISMATCH", "later"

# The first cell of each row of the mapping table, in order. If the handoff table changes, the
# check reports it instead of quietly checking an outdated list.
SOURCE_FIELDS = (
    "All ZIPs and CSV/text files",
    "11 `disease`",
    "11 `symptom_*`, `rare_symptom_*`",
    "12 data.csv `diseases`",
    "12 data.csv other 377 columns",
    "12 final_symptoms_to_disease.csv `diseases`, `symptom_text`",
    "13 diseases_main.csv `id`, `name`",
    "13 `category`",
    "13 `summary`",
    "13 `word_count`, `url`",
    "13 causes.csv `disease_id`, `disease_name`, `cause`",
    "13 symptoms.csv `disease_id`, `disease_name`, `symptom`",
    "13 treatments.csv `disease_id`, `disease_name`, `treatment`",
    "13 text files",
    "14 `Patient_ID`",
    "14 `Age`",
    "14 `Gender`",
    "14 `Symptoms`",
    "14 `Symptom_Count`",
    "14 `Disease`",
    "15 `PATIENT_ID`, `AGE`, `SEX`, `DISEASE`",
    "15 `E_*` (223 positions)",
    "15 `SYMPTOM_COUNT`",
    "16 matrix `diseases`",
    "16 matrix other 654 positions",
    "16 descriptions `Disease`, `Description`",
    "16 `Source`, `Source_URL`, `Retrieved_Date`, `Canonical_Query`",
)

_FEATURE_ROWS = """SELECT cf.mapping_id, r.source_id, count(*),
       count(*) FILTER (WHERE cf.presence = 'present'), count(*) FILTER (WHERE cf.conflict),
       count(*) FILTER (WHERE cf.raw_value = '0' AND NOT cf.conflict),
       count(*) FILTER (WHERE cf.presence = 'absent'), count(*) FILTER (WHERE cf.presence = 'not_asked'),
       count(*) FILTER (WHERE cf.presence = 'uncertain' AND NOT cf.conflict)
FROM case_features cf JOIN dataset_cases c USING (case_id) JOIN source_records r USING (record_id)
WHERE cf.mapping_id = ANY(%s) GROUP BY 1, 2"""

FEATURE_COUNTS = ("rows", "present", "conflict", "zero_outside", "absent", "not_asked", "uncertain_outside")
NO_ROWS = {**dict.fromkeys(FEATURE_COUNTS, 0), "foreign": 0}


@dataclass(frozen=True)
class Check:
    row: int  # row of the mapping table (1-based); 0 = the M1 acceptance criteria of docs/05
    measure: str
    expected: Any
    loaded: Any
    basis: str
    status: str


class Report:
    def __init__(self, table: list[tuple[str, str, str]]) -> None:
        self.table = table
        self.checks: list[Check] = []

    def check(self, row: int, measure: str, expected: Any, loaded: Any, basis: str) -> None:
        self.checks.append(Check(row, measure, expected, loaded, basis, OK if expected == loaded else MISMATCH))

    def later(self, row: int, measure: str, loaded: Any, owner: str) -> None:
        """Work the mapping table asks for that a later sub-step owns. Reported, never passed."""
        self.checks.append(Check(row, measure, f"done in {owner}", loaded, "plan", LATER))

    def close(self) -> None:
        """A row of the mapping table without any check is itself a mismatch."""
        covered = {check.row for check in self.checks}
        for number in range(1, len(self.table) + 1):
            if number not in covered:
                self.check(number, "a check exists for this row", "at least one", "none", "this command")

    @property
    def mismatches(self) -> list[Check]:
        return [check for check in self.checks if check.status == MISMATCH]

    @property
    def deferred(self) -> list[Check]:
        return [check for check in self.checks if check.status == LATER]


def mapping_table(path: Path = DOC) -> list[tuple[str, str, str]]:
    """(source field, target, transformation) for every row of the handoff's mapping table."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[tuple[str, str, str]] = []
    for line in lines[lines.index(TABLE_HEADING) + 1 :]:
        if line.startswith("## "):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) != 3 or not cells[0].strip("-") or cells[1] == "Target":
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def _fmt(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        return str(value)
    return f"{value:,}"


def render(report: Report) -> str:
    lines = []
    for number in sorted({check.row for check in report.checks}):
        if number == 0:
            lines.append("\nM1 acceptance criteria (docs/05_IMPLEMENTATION_BACKLOG.md)")
        elif number <= len(report.table):
            field, target, _ = report.table[number - 1]
            lines.append(f"\n[T{number}] {field}  ->  {target}")
        else:
            lines.append(f"\n[T{number}] (not a row of the mapping table)")
        for check in (c for c in report.checks if c.row == number):
            lines.append(
                f"  {check.status:<8} {check.measure}: expected {_fmt(check.expected)}, "
                f"loaded {_fmt(check.loaded)}  [{check.basis}]"
            )
    return "\n".join(lines)


def _member_sha256(archive: zipfile.ZipFile, member: str) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _reference(cur: Any, source_ids: list[str], release_id: str = RELEASE_ID) -> dict[str, Any]:
    """Sources, mappings and features as stored. Small tables, read whole."""
    cur.execute(f"SELECT source_id, version, sha256, {standing('sources')} FROM sources")
    sources = {row[0]: row[1:] for row in cur.fetchall()}
    disease: dict[str, dict[str, tuple[Any, ...]]] = {}
    cur.execute(
        f"SELECT source_id, original_label, disease_id, original_id, method, {standing('disease_mappings')} "
        "FROM disease_mappings WHERE release_id = %s AND source_id = ANY(%s)",
        (release_id, source_ids),
    )
    for sid, label, *rest in cur.fetchall():
        disease.setdefault(sid, {})[label] = tuple(rest)
    positional: dict[str, dict[int, dict[str, Any]]] = {}
    listed: dict[str, dict[str, dict[str, Any]]] = {}
    cur.execute(
        f"""SELECT mapping_id, source_id, column_index, original_term, feature_id, zero_semantics,
                  {standing("feature_mappings")}, transformation ->> 'candidate_term'
           FROM feature_mappings WHERE release_id = %s AND source_id = ANY(%s)""",
        (release_id, source_ids),
    )
    for mapping_id, sid, index, term, feature_id, zero, status, candidate in cur.fetchall():
        mapping = {"id": mapping_id, "term": term, "feature": feature_id, "zero": zero, "status": status}
        if index is None:
            listed.setdefault(sid, {})[candidate] = mapping
        else:
            positional.setdefault(sid, {})[int(index)] = mapping
    cur.execute(f"SELECT feature_id, kind::text, {standing('features')} FROM features")
    features = {row[0]: row[1:] for row in cur.fetchall()}
    cur.execute(
        """SELECT source_id, count(*), count(DISTINCT content_hash), count(DISTINCT row_number), min(row_number),
                  max(row_number), count(*) FILTER (WHERE coalesce(raw_object_uri, '') = '')
           FROM source_records WHERE source_id = ANY(%s) AND row_number IS NOT NULL GROUP BY 1""",
        (source_ids,),
    )
    records = {row[0]: row[1:] for row in cur.fetchall()}
    cur.execute("SELECT status::text FROM mapping_releases WHERE release_id = %s", (release_id,))
    release = cur.fetchone()
    cur.execute(
        f"""SELECT count(*) FROM diseases WHERE {changed_by_no_reviewer("diseases")} AND disease_id IN (
               SELECT disease_id FROM disease_mappings WHERE release_id = %s AND source_id = ANY(%s))""",
        (release_id, source_ids),
    )
    unreviewed_diseases = cur.fetchone()[0]
    return {
        "sources": sources,
        "disease": disease,
        "positional": positional,
        "listed": listed,
        "features": features,
        "records": records,
        "mapping_release_status": release[0] if release else None,
        "diseases_changed_by_no_reviewer": unreviewed_diseases,
    }


def _feature_rows(cur: Any, reference: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Stored feature values per mapping, in one pass over `case_features`. `foreign` counts the
    rows attached to a case that belongs to another source file."""
    owner = {}
    for group in (reference["positional"], reference["listed"]):
        for sid, mappings in group.items():
            owner.update({mapping["id"]: sid for mapping in mappings.values()})
    stored: dict[str, dict[str, int]] = {}
    cur.execute(_FEATURE_ROWS, (list(owner),))
    for mapping_id, case_source, *counts in cur.fetchall():
        entry = stored.setdefault(mapping_id, dict(NO_ROWS))
        for name, count in zip(FEATURE_COUNTS, counts, strict=True):
            entry[name] += count
        if case_source != owner[mapping_id]:
            entry["foreign"] += counts[0]
    return stored


def _evidence(cur: Any, files: dict[tuple[str, str], dict[str, Any]], narrative_sid: str) -> dict[str, Any]:
    """Proposals as stored, and the narrative mentions recomputed from the stored statements."""
    case_sources = {whole_file_record_id(f["sid"]): key for key, f in files.items() if f["kind"] == "case"}
    cooccurrence: dict[tuple[str, str], dict[tuple[str, str], tuple[Any, ...]]] = {key: {} for key in files}
    cur.execute(
        f"""SELECT record_id, disease_id, feature_id, (context ->> 'cases_with_feature')::bigint,
                  frequency_denominator, frequency, {standing("disease_feature_evidence")}
           FROM disease_feature_evidence WHERE evidence_type = %s AND record_id = ANY(%s)""",
        (COOCCURRENCE_TYPE, list(case_sources)),
    )
    for record_id, disease_id, feature_id, *rest in cur.fetchall():
        cooccurrence[case_sources[record_id]][(disease_id, feature_id)] = tuple(rest)

    cur.execute("SELECT feature_id, preferred_name FROM features WHERE feature_id LIKE %s", ("feat\\_%",))
    terms = {
        name: feature_id
        for feature_id, name in cur.fetchall()
        if len(name) >= MIN_TERM_LENGTH and not _QUESTION_TERM.match(name)
    }
    cur.execute(
        """SELECT DISTINCT st.statement_id, st.text_content
           FROM statements st JOIN statement_sources ss USING (statement_id)
           JOIN source_records r USING (record_id)
           WHERE st.statement_type = 'symptom' AND st.disease_id IS NOT NULL AND r.source_id = %s""",
        (narrative_sid,),
    )
    statements = dict(cur.fetchall())
    expected: set[tuple[str, str]] = set()
    if terms:
        pattern = term_pattern(list(terms))
        for statement_id, text in statements.items():
            expected.update((statement_id, feature_id) for feature_id in find_mentions(text, pattern, terms))
    cur.execute(
        f"SELECT statement_id, feature_id, {standing('disease_feature_evidence')} FROM disease_feature_evidence "
        "WHERE evidence_type = %s AND statement_id = ANY(%s)",
        (NARRATIVE_TYPE, list(statements)),
    )
    stored = {(statement_id, feature_id): status for statement_id, feature_id, status in cur.fetchall()}
    cur.execute(
        """SELECT st.statement_type, count(DISTINCT e.evidence_id)
           FROM disease_feature_evidence e JOIN statements st USING (statement_id)
           WHERE e.statement_id IN (SELECT ss.statement_id FROM statement_sources ss
                                    JOIN source_records r USING (record_id) WHERE r.source_id = ANY(%s))
           GROUP BY 1""",
        ([f["sid"] for f in files.values() if f["kind"] == "statement"],),
    )
    return {
        "cooccurrence": cooccurrence,
        "mentions_expected": len(expected),
        "mentions": len(expected & set(stored)),
        "mentions_unexpected": len(set(stored) - expected),
        "mentions_changed_by_no_reviewer": sum(1 for status in stored.values() if status not in IN_ORDER),
        "by_statement_type": dict(cur.fetchall()),
    }


def _archives(
    cur: Any, raw_dir: Path, manifest: Manifest, settings: ObjectStoreSettings | None, s3: Any
) -> dict[str, Any]:
    """The registry of stored archives, and the stored bytes themselves re-read and hashed."""
    cur.execute(
        "SELECT archive_name, sha256, size_bytes, bucket, object_key, verified_at IS NOT NULL "
        "FROM source_archives WHERE archive_name = ANY(%s)",
        (list(manifest.archives),),
    )
    rows = cur.fetchall()
    registered = [
        row
        for row in rows
        if row[1] == manifest.archives[row[0]] and row[2] == (raw_dir / row[0]).stat().st_size and row[5]
    ]
    facts: dict[str, Any] = {"registered": len(registered), "stored": 0, "problem": None}
    try:
        client = s3 or make_client(settings or ObjectStoreSettings())
        for name, digest, _size, bucket, key, _verified in registered:
            facts["stored"] += _stored_digest(client, bucket, key)[0] == digest == manifest.archives[name]
    except (Exception, SystemExit) as error:  # not configured or not reachable: reported, never assumed
        facts["problem"] = f"{type(error).__name__}: {error}"
    return facts


def narrative_expectations(main_rows: list[dict[str, str]]) -> dict[str, Callable[[dict[str, str]], dict[str, Any]]]:
    """Per narrative adapter: what the mapping table requires of one source row (disease label,
    statement type, text, URL, attribution kept beside the statement, quality flags)."""
    by_native = {row.get("id", ""): row for row in main_rows}

    def main_table(row: dict[str, str]) -> dict[str, Any]:
        words = row["word_count"]
        span = {
            "column": "summary",
            "native_id": row["id"],
            "source_category": row["category"],
            "word_count": int(words) if words.isdigit() else words,
        }
        return {
            "label": row["name"],
            "type": "description",
            "text": row["summary"],
            "url": row["url"],
            "span": span,
            "flags": [CATEGORY_FLAG],
        }

    def narrative(row: dict[str, str]) -> dict[str, Any]:
        column = list(row)[2]  # causes.csv -> cause, symptoms.csv -> symptom, treatments.csv -> treatment
        main = by_native.get(row["disease_id"])
        flags = []
        if main is None:
            flags.append("unknown_native_disease_id")
        elif norm_label(main["name"]) != norm_label(row["disease_name"]):
            flags.append("disease_name_disagrees_with_diseases_main")
        return {
            "label": main["name"] if main else row["disease_name"],
            "type": column,
            "text": row[column],
            "url": main["url"] if main else None,
            "span": {"column": column, "native_id": row["disease_id"]},
            "flags": flags,
        }

    def description(row: dict[str, str]) -> dict[str, Any]:
        span = {
            "column": "Description",
            "source": row["Source"],
            "retrieved_date": row["Retrieved_Date"],
            "canonical_query": row["Canonical_Query"],
        }
        return {
            "label": row["Disease"],
            "type": "description",
            "text": row["Description"],
            "url": row["Source_URL"],
            "span": span,
            "flags": [],
        }

    return {"disease_metadata": main_table, "narrative": narrative, "disease_description": description}


def inspect_file(
    cur: Any,
    archive: zipfile.ZipFile,
    info: dict[str, Any],
    reference: dict[str, Any],
    manifest: Manifest,
    profiles: dict[str, dict[Any, Any]],
    expectations: dict[str, Callable[[dict[str, str]], dict[str, Any]]],
) -> None:
    """Fill `info` for one CSV file: its layout, and the row-by-row comparison (`facts`).
    `facts` stays None when the file does not have its registered layout (source schema drift)."""
    entry, sid = info["entry"], info["sid"]
    archive_name, name = entry["archive"], entry["file"]
    header, _ = read_csv_positional(archive, name)
    mapped = reference["positional"].get(sid, {})
    roles = role_positions(header)
    info["header"] = header
    info["member_sha256"] = _member_sha256(archive, name)
    info["headings_in_place"] = sum(
        1 for index, mapping in mapped.items() if index < len(header) and header[index] == mapping["term"]
    )
    info["facts"] = None
    as_registered = len(header) == entry.get("expected_columns", len(header))
    if info["kind"] == "case":
        info["columns_with_a_target"] = len(set(mapped) | set(roles.values()))
        if as_registered and "label" in roles:
            info["facts"] = verify_case_file(
                cur,
                archive,
                archive_name,
                name,
                sid,
                original_split(archive_name, name, manifest),
                {index: mapping["feature"] for index, mapping in mapped.items()},
                {term: mapping["feature"] for term, mapping in reference["listed"].get(sid, {}).items()},
                profiles,
            )
    else:
        info["columns_with_a_target"] = len(header)
        if as_registered and set(ADAPTER_COLUMNS[entry["adapter"]]) <= set(header):
            info["facts"] = verify_statement_file(cur, archive, name, sid, expectations[entry["adapter"]])


def gather(
    cur: Any,
    raw_dir: Path,
    manifest: Manifest,
    settings: ObjectStoreSettings | None = None,
    s3: Any = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Everything the row checks need: stored state, recounts and the handoff's own numbers."""
    audit = json.loads(REFERENCE_AUDIT.read_text(encoding="utf-8"))
    disease_cross: dict[tuple[str, str], dict[str, str]] = {}
    for row in _csv_rows(AUDIT_DIR / "disease_mappings.csv"):
        disease_cross.setdefault((row["archive"], row["file"]), {})[row["source_label"]] = row["candidate_disease_id"]
    feature_cross: dict[tuple[str, str], dict[int, tuple[str, str]]] = {}
    for row in _csv_rows(AUDIT_DIR / "feature_column_mappings.csv"):
        feature_cross.setdefault((row["archive"], row["file"]), {})[int(row["column_index"])] = (
            row["original_header"],
            row["candidate_feature_id"],
        )
    files: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in manifest.files:
        files[(entry["archive"], entry["file"])] = {
            "entry": entry,
            "sid": source_id(entry["archive"], entry["file"]),
            "kind": "case" if "dataset_cases" in entry["targets"] else "statement",
        }
    text_sid = source_id(TEXT_ARCHIVE, "*.txt")
    reference = _reference(cur, [f["sid"] for f in files.values()] + [text_sid])
    archives = {name: zipfile.ZipFile(raw_dir / name) for name in manifest.archives}
    try:
        main_header, main_cells = read_csv_positional(archives[TEXT_ARCHIVE], "diseases_main.csv")
        main_rows = [dict(zip(main_header, cells, strict=False)) for cells in main_cells]
        expectations = narrative_expectations(main_rows)
        profiles: dict[str, dict[str, dict[Any, Any]]] = {}
        for (archive, name), info in files.items():
            progress(f"reading {archive}/{name}")
            inspect_file(
                cur, archives[archive], info, reference, manifest, profiles.setdefault(archive, {}), expectations
            )
        progress("reading the narrative text files")
        texts = verify_text_files(
            cur,
            archives[TEXT_ARCHIVE],
            [text for text in manifest.text_files if text["archive"] == TEXT_ARCHIVE],
            text_sid,
            KNOWLEDGE_RELEASE_ID,
        )
    finally:
        for archive_file in archives.values():
            archive_file.close()
    cur.execute(
        "SELECT count(*) FROM source_records WHERE row_number IS NULL AND record_id = ANY(%s)",
        ([whole_file_record_id(f["sid"]) for f in files.values() if f["kind"] == "case"],),
    )
    whole_file_records = cur.fetchone()[0]
    cur.execute(
        "SELECT count(*) FROM statement_sources ss JOIN source_records r USING (record_id) WHERE r.source_id = %s",
        (text_sid,),
    )
    text_statements = cur.fetchone()[0]
    progress("counting the stored feature values (about two minutes on the full data)")
    feature_rows = _feature_rows(cur, reference)
    progress("reading the evidence proposals and the archive registry")
    return {
        "manifest": manifest,
        "audit": audit,
        "audit_files": {(f["archive"], f["file"]): f for f in audit["files"]},
        "disease_cross": disease_cross,
        "feature_cross": feature_cross,
        "files": files,
        "reference": reference,
        "text_sid": text_sid,
        "texts": texts,
        "main_rows": main_rows,
        "whole_file_records": whole_file_records,
        "text_statements": text_statements,
        "feature_rows": feature_rows,
        "evidence": _evidence(cur, files, source_id(TEXT_ARCHIVE, "symptoms.csv")),
        "claims": _claims(cur, source_id(TEXT_ARCHIVE, "symptoms.csv")),
        "archives": _archives(cur, raw_dir, manifest, settings, s3),
    }


def rows_recognised(table: list[tuple[str, str, str]]) -> int | str:
    """How many rows of the handoff table are the rows this check was written for."""
    fields = [row[0] for row in table]
    if len(fields) != len(SOURCE_FIELDS):
        return f"{len(fields)} rows in the document"
    return sum(1 for mine, theirs in zip(SOURCE_FIELDS, fields, strict=True) if mine == theirs)


def run_completeness(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    settings: ObjectStoreSettings | None = None,
    s3: Any = None,
    doc_path: Path = DOC,
    progress: Callable[[str], None] = lambda _message: None,
) -> Report:
    """Run every check and return the report. Reads only; the transaction is READ ONLY."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)  # checksums and ZIP safety before anything is read
    report = Report(mapping_table(doc_path))
    report.check(
        0,
        "rows of the mapping table that this check was written for",
        len(SOURCE_FIELDS),
        rows_recognised(report.table),
        "docs/04",
    )
    engine = create_engine(database_url)
    try:
        with _raw_cursor(engine) as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL work_mem = '512MB'")
            world = gather(cur, raw_dir, manifest, settings, s3, progress)
    finally:
        engine.dispose()
    emit(report, world)
    report.close()
    return report


def _claims(cur: Any, narrative_sid: str) -> dict[str, int]:
    """The single claims of the symptom statements (M2.6): recomputed from the stored statements by the rules,
    and compared with what is stored."""
    from .claims import split
    from .claims_load import claim_id

    cur.execute(
        """SELECT DISTINCT st.statement_id, st.text_content
           FROM statements st JOIN statement_sources ss USING (statement_id)
           JOIN source_records r USING (record_id)
           WHERE st.statement_type = 'symptom' AND r.source_id = %s""",
        (narrative_sid,),
    )
    statements = dict(cur.fetchall())
    expected = {
        claim_id(statement_id, claim.kind, claim.start, claim.end)
        for statement_id, text in statements.items()
        for claim in split(text)[0]
    }
    cur.execute(
        """SELECT c.claim_id, c.status::text, c.reviewer,
                  substr(st.text_content, c.span_start + 1, c.span_end - c.span_start) = c.claim_text
           FROM statement_claims c JOIN statements st USING (statement_id) WHERE c.statement_id = ANY(%s)""",
        (list(statements),),
    )
    stored = {row[0]: row[1:] for row in cur.fetchall()}
    return {
        "statements": len(statements),
        "expected": len(expected),
        "stored_as_expected": len(expected & set(stored)),
        "unexpected": len(set(stored) - expected),
        "not_their_text": sum(1 for _status, _reviewer, same in stored.values() if not same),
        "decided_without_reviewer": sum(
            1 for status, reviewer, _same in stored.values() if status != "pending" and not reviewer
        ),
    }
