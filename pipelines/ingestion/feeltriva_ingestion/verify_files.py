"""Per-file verification for the ingestion completeness check (M1.13).

Each function reads one source file straight from its archive and, in the same pass, the rows
the loaders stored for it, and returns plain counts. Nothing here writes; the caller runs it in
a read-only transaction.

The expected side is recounted from the file by code that does not reuse the loaders' counting
logic (only their ID and hash functions, which define what "the same row" means). A loader
mistake therefore cannot hide behind itself.

All counts are counts of rows and cells in files: not patients, not prevalence.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import zipfile
from collections import Counter
from collections.abc import Callable, Generator, Iterator
from operator import itemgetter
from typing import Any

from .archives import read_csv_positional
from .audit import DISEASE_HEADERS, norm_label
from .cases import _hash
from .chunks import ChunkingError, chunk_document, uncovered_characters
from .load import _h, disease_candidate_id

# Columns of a case file that are not feature columns, by what the loaders do with them.
ROLE_HEADERS: dict[str, tuple[str, ...]] = {
    "label": DISEASE_HEADERS,
    "patient_id": ("patient_id",),
    "age": ("age",),
    "demographic": ("sex", "gender"),
    "list": ("symptom_text", "symptoms"),
    "declared_count": ("symptom_count",),
}

_CASE_ROWS = """SELECT r.row_number, r.content_hash, r.quality_flags, r.original_split, r.raw_object_uri,
       c.case_id, c.source_patient_id, c.source_split, c.age_value, c.age_unit,
       c.original_demographic_field, c.original_demographic_value, c.profile_cluster_id, c.duplicate_status,
       l.original_label, l.disease_id, l.label_origin
FROM source_records r LEFT JOIN dataset_cases c USING (record_id) LEFT JOIN case_labels l USING (case_id)
WHERE r.source_id = %s AND r.row_number IS NOT NULL ORDER BY r.row_number, l.disease_id"""

_STATEMENT_ROWS = """SELECT r.row_number, r.content_hash, r.quality_flags, ss.source_url, ss.text_span,
       st.statement_id, st.statement_type, st.text_content, st.status::text, st.disease_id
FROM source_records r LEFT JOIN statement_sources ss USING (record_id) LEFT JOIN statements st USING (statement_id)
WHERE r.source_id = %s AND r.row_number IS NOT NULL ORDER BY r.row_number, st.statement_id"""

_cursor_names = itertools.count(1)


def stream(cur: Any, query: str, params: tuple[Any, ...]) -> Generator[tuple[Any, ...]]:
    """Rows through a server-side cursor: they arrive in batches, never a whole table at once."""
    server = cur.connection.cursor(name=f"completeness_{next(_cursor_names)}")
    server.itersize = 20_000
    try:
        server.execute(query, params)
        yield from server
    finally:
        server.close()


def role_positions(header: list[str]) -> dict[str, int]:
    """Position of each non-feature column that is present, by role."""
    lowered = [c.lower() for c in header]
    found = {}
    for role, names in ROLE_HEADERS.items():
        position = next((i for i, c in enumerate(lowered) if c in names), None)
        if position is not None:
            found[role] = position
    return found


def _number(raw: str) -> float | None:
    """A finite, non-negative number, or None. The rule for an age value that can be kept."""
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _by_row(rows: Iterator[tuple[Any, ...]]) -> Iterator[tuple[int, list[tuple[Any, ...]]]]:
    for number, group in itertools.groupby(rows, key=itemgetter(0)):
        yield number, list(group)


def verify_case_file(
    cur: Any,
    archive: zipfile.ZipFile,
    archive_name: str,
    file: str,
    sid: str,
    split: str | None,
    columns: dict[int, str],
    list_features: dict[str, str],
    profiles: dict[str, dict[Any, Any]],
) -> dict[str, Any]:
    """Recount one case file and compare every row with what is stored for it.

    columns: registered feature column position -> feature ID. list_features: normalised list
    term -> feature ID. profiles: shared by the files of one archive, so that equal profiles in
    different files (archive 15 train/test) must carry the same cluster ID.
    """
    header, reader = read_csv_positional(archive, file)
    width = len(header)
    at = role_positions(header)
    label_i, id_i, age_i = at["label"], at.get("patient_id"), at.get("age")
    demo_i, list_i, count_i = at.get("demographic"), at.get("list"), at.get("declared_count")
    order = sorted(columns)
    names = Counter(header[i] for i in order)
    repeated = {name: [i for i in order if header[i] == name] for name, n in names.items() if n > 1}
    kept = [i for i in range(width) if i != label_i and i != id_i]
    pick: Callable[[list[str]], Any] = itemgetter(*kept) if len(kept) > 1 else (lambda c: tuple(c[i] for i in kept))
    layout = hash((archive_name, tuple(c for i, c in enumerate(header) if i != id_i)))
    by_key, by_cluster = profiles.setdefault("by_key", {}), profiles.setdefault("by_cluster", {})

    facts: dict[str, Any] = {
        "header": header,
        "rows": 0,
        "malformed": 0,
        "aligned": True,
        "cases": 0,
        "extra_label_rows": 0,
        "row_diffs": Counter(),
        "flags": Counter(),
        "duplicate_status": Counter(),
        "label_origin": Counter(),
        "age_unit_set": 0,
        "age_not_parsed": 0,
        "cluster_diffs": 0,
        "stored_labels": set(),
        "stored_demographic": Counter(),
        "stored_pairs": set(),
        "profile_rows": Counter(),
        "column_rows": [0] * width,
        "column_present": [0] * width,
        "conflict_cases": Counter(),
        "conflict_rows": 0,
        "conflict_zero_rows": 0,
        "blank_cells": 0,
        "other_value_cells": 0,
        "items": 0,
        "duplicate_items": 0,
        "empty_lists": 0,
        "term_cases": Counter(),
        "declared_count_mismatches": 0 if count_i is not None else None,
        "label_cases": Counter(),
        "cooccurrence": {},
    }
    diffs, column_rows, column_present = facts["row_diffs"], facts["column_rows"], facts["column_present"]
    content_rows: Counter[int] = Counter()
    stored_rows = stream(cur, _CASE_ROWS, (sid,))
    groups = _by_row(stored_rows)
    try:
        for n, cells in enumerate(reader, start=1):
            facts["rows"] += 1
            content = _hash(*cells)
            content_rows[hash(content)] += 1
            malformed = len(cells) != width
            stored = None
            if facts["aligned"]:
                number, group = next(groups, (None, []))
                if number != n:  # a record is missing, extra or out of order: stop comparing rows
                    facts["aligned"] = False
                else:
                    stored = group[0]
                    facts["extra_label_rows"] += len(group) - 1
                    facts["flags"].update(stored[2] or ())
                    if stored[1] != content:
                        diffs["content hash"] += 1
                    if not stored[4] or stored[3] != split:
                        diffs["row locator or original split"] += 1
                    if (stored[5] is None) != malformed:
                        diffs["case exists for the row"] += 1
                        stored = None
            if malformed:
                facts["malformed"] += 1
                continue

            label = cells[label_i]
            disease_id = disease_candidate_id(label)
            facts["label_cases"][disease_id] += 1
            key = hash((layout, pick(cells)))
            facts["profile_rows"][key] += 1
            age = _number(cells[age_i]) if age_i is not None else None
            if age_i is not None and age is None:
                facts["age_not_parsed"] += 1

            if stored is not None:
                facts["cases"] += 1
                if stored[6] != (cells[id_i] if id_i is not None else None):
                    diffs["patient id"] += 1
                if (stored[8] is None) != (age is None) or (age is not None and float(stored[8]) != age):
                    diffs["age"] += 1
                if stored[9] is not None:
                    facts["age_unit_set"] += 1
                supplied = (header[demo_i], cells[demo_i]) if demo_i is not None else (None, None)
                if (stored[10], stored[11]) != supplied:
                    diffs["demographic field or value"] += 1
                if stored[14] != label or stored[15] != disease_id:
                    diffs["label or its lexical candidate"] += 1
                if stored[7] != split:
                    diffs["split"] += 1
                facts["duplicate_status"][stored[13]] += 1
                facts["label_origin"][stored[16]] += 1
                facts["stored_labels"].add(stored[14])
                facts["stored_pairs"].add(hash((stored[12], stored[14])))
                if demo_i is not None:
                    facts["stored_demographic"][stored[11]] += 1
                # Equal profiles must share one cluster ID, and one cluster ID must mean one profile.
                if by_key.setdefault(key, stored[12]) != stored[12] or by_cluster.setdefault(stored[12], key) != key:
                    facts["cluster_diffs"] += 1

            present: set[str] = set()
            ones = 0
            if order:
                conflicted: set[int] = set()
                for name, positions in repeated.items():
                    first = cells[positions[0]]
                    if any(cells[p] != first for p in positions[1:]):
                        conflicted.update(positions)
                        facts["conflict_cases"][name] += 1
                for i in [i for i in order if cells[i] != "0"]:
                    column_rows[i] += 1  # every non-zero cell is a stored row
                    value = cells[i]
                    ones += value == "1"
                    if i in conflicted:
                        continue
                    if value == "1":
                        column_present[i] += 1
                        present.add(columns[i])
                    elif value == "":
                        facts["blank_cells"] += 1
                    else:
                        facts["other_value_cells"] += 1
                for i in conflicted:  # a conflict keeps every position, the zero side included
                    facts["conflict_rows"] += 1
                    if cells[i] == "0":
                        column_rows[i] += 1
                        facts["conflict_zero_rows"] += 1
            listed = None
            if list_i is not None:
                items = [item for item in (part.strip() for part in cells[list_i].split(",")) if item]
                terms = {norm_label(item) for item in items}
                listed = len(items)
                facts["items"] += listed
                facts["duplicate_items"] += listed - len(terms)
                facts["empty_lists"] += not items
                facts["term_cases"].update(terms)
                present.update(list_features.get(term, f"unmapped:{term}") for term in terms)
            if count_i is not None and cells[count_i].strip() != str(ones if listed is None else listed):
                facts["declared_count_mismatches"] += 1
            if present:
                facts["cooccurrence"].setdefault(disease_id, Counter()).update(present)
        if facts["aligned"] and next(groups, None) is not None:
            facts["aligned"] = False  # records exist beyond the last row of the file
    finally:
        stored_rows.close()
    facts["distinct_content"] = len(content_rows)
    facts["rows_in_exact_duplicate_groups"] = sum(n for n in content_rows.values() if n > 1)
    return facts


def verify_statement_file(
    cur: Any, archive: zipfile.ZipFile, file: str, sid: str, expect: Callable[[dict[str, str]], dict[str, Any]]
) -> dict[str, Any]:
    """Compare a narrative table with its records, statements and attributions, row by row.

    `expect(row)` says what the mapping table requires of one source row: disease label,
    statement type, text, URL, the attribution fields kept beside the statement, and flags.
    """
    header, reader = read_csv_positional(archive, file)
    facts: dict[str, Any] = {
        "header": header,
        "rows": 0,
        "malformed": 0,
        "aligned": True,
        "row_diffs": Counter(),
        "flags": Counter(),
        "expected_flags": Counter(),
        "links_expected": 0,
        "links": 0,
        "not_pending": 0,
        "attribution_rows": Counter(),
        "labels": set(),
    }
    diffs = facts["row_diffs"]
    content: set[str] = set()
    wanted: set[tuple[str, str, str]] = set()
    statement_ids: set[str] = set()
    stored_rows = stream(cur, _STATEMENT_ROWS, (sid,))
    groups = _by_row(stored_rows)
    try:
        for n, cells in enumerate(reader, start=1):
            facts["rows"] += 1
            digest = _h(*cells)
            content.add(digest)
            if len(cells) != len(header):
                facts["malformed"] += 1
                continue
            want = expect(dict(zip(header, cells, strict=True)))
            disease_id = disease_candidate_id(want["label"])
            has_text = bool(want["text"].strip())
            facts["labels"].add(want["label"])
            facts["expected_flags"].update(want["flags"])
            if has_text:
                facts["links_expected"] += 1
                wanted.add((disease_id, want["type"], norm_label(want["text"])))
            if not facts["aligned"]:
                continue
            number, group = next(groups, (None, []))
            if number != n:
                facts["aligned"] = False
                continue
            facts["flags"].update(group[0][2] or ())
            if group[0][1] != digest:
                diffs["content hash"] += 1
            linked = [row for row in group if row[5] is not None]
            if len(linked) != (1 if has_text else 0):
                diffs["one statement per row with text"] += 1
                continue
            if not has_text:
                continue
            _, _, _, url, span, statement_id, statement_type, text, status, stored_disease = linked[0]
            facts["links"] += 1
            statement_ids.add(statement_id)
            facts["not_pending"] += status != "pending"
            if (
                statement_type != want["type"]
                or norm_label(text) != norm_label(want["text"])
                or stored_disease != disease_id
            ):
                diffs["statement text, type or disease"] += 1
            if (url or None) == (want["url"] or None):
                facts["attribution_rows"]["source_url"] += 1
            else:
                diffs["source url"] += 1
            for field, value in want["span"].items():
                if (span or {}).get(field) == value:
                    facts["attribution_rows"][field] += 1
                else:
                    diffs[f"attribution field {field}"] += 1
        if facts["aligned"] and next(groups, None) is not None:
            facts["aligned"] = False
    finally:
        stored_rows.close()
    facts["distinct_content"] = len(content)
    facts["statements_expected"] = len(wanted)
    facts["statements"] = len(statement_ids)
    return facts


def verify_text_files(
    cur: Any, archive: zipfile.ZipFile, texts: list[dict[str, Any]], text_sid: str, release_id: str
) -> dict[str, Any]:
    """The narrative text files: one record per file with its digest, and chunks whose stored
    offsets reproduce the stored text from the file exactly."""
    cur.execute("SELECT file_path, record_id, content_hash FROM source_records WHERE source_id = %s", (text_sid,))
    records = {path: (record_id, digest) for path, record_id, digest in cur.fetchall()}
    cur.execute(
        "SELECT record_id, chunk_text, metadata, search_vector IS NOT NULL FROM evidence_chunks "
        "WHERE knowledge_release_id = %s",
        (release_id,),
    )
    chunks: dict[str, list[tuple[str, dict[str, Any], bool]]] = {}
    for record_id, text, metadata, searchable in cur.fetchall():
        chunks.setdefault(record_id, []).append((text, metadata, searchable))
    cur.execute("SELECT status::text FROM knowledge_releases WHERE release_id = %s", (release_id,))
    release = cur.fetchone()
    facts: dict[str, Any] = {
        "files": len(texts),
        "records": len(records),
        "records_with_file_digest": 0,
        "unreadable": 0,
        "documents_with_chunks": 0,
        "chunks_expected": 0,
        "chunks": 0,
        "offsets_reproduce_text": 0,
        "with_attribution": 0,
        "with_source_category": 0,
        "searchable": 0,
        "uncovered_characters": 0,
        "release_status": release[0] if release else None,
    }
    for entry in texts:
        raw = archive.read(entry["file"])
        digest = hashlib.sha256(raw).hexdigest()
        record_id, stored_digest = records.get(entry["file"], (None, None))
        facts["records_with_file_digest"] += stored_digest == digest == entry["sha256"]
        text = raw.decode("utf-8")
        try:
            document = chunk_document(text)
        except ChunkingError:
            facts["unreadable"] += 1
            continue
        facts["chunks_expected"] += len(document.chunks)
        facts["uncovered_characters"] += uncovered_characters(text, document)
        stored = chunks.get(record_id or "", [])
        facts["documents_with_chunks"] += bool(stored)
        for chunk_text, metadata, searchable in stored:
            facts["chunks"] += 1
            facts["searchable"] += searchable
            start, end = metadata.get("char_start"), metadata.get("char_end")
            facts["offsets_reproduce_text"] += (
                isinstance(start, int) and isinstance(end, int) and text[start:end] == chunk_text
            )
            facts["with_attribution"] += (
                metadata.get("source_url") == document.url
                and metadata.get("disease_label") == document.disease
                and metadata.get("document_sha256") == digest
                and bool(metadata.get("extraction_version"))
            )
            facts["with_source_category"] += metadata.get("source_category_unreviewed") == document.category
    return facts
