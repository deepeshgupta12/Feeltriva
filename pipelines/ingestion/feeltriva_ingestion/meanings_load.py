"""Feature meanings derived from the supplied data (M2.7): reading the files, storing proposals.

`derive_meanings` reads every case file once, applies the rules of `meanings.py` and stores the
result as proposals:

- on each column or list-term mapping: `transformation.meaning` (kind, zero meaning, the rule
  and basis of each, how often the column is affirmed) and `zero_semantics`;
- on each feature: `kind`, when the wording settles it;
- on each source: `population` (the range of its age column and the proposed unit; whether the
  same cases also exist in another file of the archive).

Nothing is approved and no status changes. Rows a reviewer has already decided are left alone.
A rerun writes nothing new. `dataset_cases.age_unit` is not touched: a proposed unit is not a
confirmed one.

Counts are counts of rows in files: not patients, not prevalence.
"""

from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import RAW_DIR, ROOT, Manifest, load_manifest, read_csv_positional, require_layouts, verify_all
from .audit import DISEASE_HEADERS, norm_label
from .cases import _raw_cursor, case_files
from .load import RELEASE_ID, source_id
from .meanings import (
    UNDECIDED,
    VERSION,
    ZERO_NO_ANSWER,
    classify_kind,
    classify_zero,
    is_cut_off,
    is_question,
    propose_age_unit,
    readable,
)
from .verify_files import role_positions

REVIEW_DIR = ROOT / "docs" / "review"
MIN_BLOCK_ROWS = 100  # a block of questions answered together must be seen in at least this many rows
_MASK = 0xFFFFFFFFFFFFFFFF


def _mix(n: int) -> int:
    """A well-spread 64-bit number for row n, so that a set of rows has a compact signature."""
    n = (n * 0x9E3779B97F4A7C15 + 0x2545F4914F6CDD1D) & _MASK
    n ^= n >> 29
    return (n * 0xBF58476D1CE4E5B9) & _MASK


def scan_file(archive: zipfile.ZipFile, file: str, terms: dict[int, str], with_bags: bool) -> dict[str, Any]:
    """One pass over a case file. `terms`: feature column position -> lexical term.

    Returns how often each column (or list term) is affirmed, a signature of the rows in which
    each column is affirmed, the age column's range, and, when asked, each case as a
    (label, set of affirmed terms) pair so that two files can be compared as collections of cases.
    """
    header, reader = read_csv_positional(archive, file)
    width, roles = len(header), role_positions(header)
    label_i, age_i, list_i = roles["label"], roles.get("age"), roles.get("list")
    order = sorted(terms)
    affirmed = dict.fromkeys(order, 0)
    signature = {i: [0, 0] for i in order}
    listed: Counter[str] = Counter()
    bags: Counter[int] = Counter()
    label_rows: Counter[str] = Counter()
    ages: list[float] = []
    age_values: set[float] = set()
    cases = unparsed_ages = 0
    for n, cells in enumerate(reader, start=1):
        if len(cells) != width:
            continue
        cases += 1
        mark = _mix(n)
        present = [i for i in order if cells[i] == "1"]
        for i in present:
            affirmed[i] += 1
            signature[i][0] ^= mark
            signature[i][1] = (signature[i][1] + mark) & _MASK
        names = {terms[i] for i in present}
        if list_i is not None:
            items = {norm_label(item) for item in cells[list_i].split(",") if item.strip()}
            listed.update(items)
            names |= items
        if with_bags:
            label = norm_label(cells[label_i])
            label_rows[label] += 1
            bags[hash((label, frozenset(names)))] += 1
        if age_i is not None:
            try:
                value = float(cells[age_i])
            except ValueError:
                unparsed_ages += 1
            else:
                age_values.add(value)
                if len(ages) < 2:
                    ages.append(value)
                ages[:] = [min(ages[0], value), max(ages[-1], value)]
    age = None
    if age_i is not None and age_values:
        age = {
            "column": header[age_i],
            "values": cases - unparsed_ages,
            "minimum": ages[0],
            "maximum": ages[1],
            "whole_numbers": all(value == int(value) for value in age_values),
            "distinct_values": len(age_values),
        }
    return {
        "header": header,
        "cases": cases,
        "affirmed": affirmed,
        "signature": {i: (affirmed[i], *signature[i]) for i in order},
        "listed": listed,
        "list_column": header[list_i] if list_i is not None else None,
        "bags": bags,
        "label_rows": label_rows,
        "age": age,
    }


def same_cases(matrix: dict[str, Any], lists: dict[str, Any]) -> dict[str, int] | None:
    """Do the cases of a list file all exist, one for one, in a matrix file of the same archive
    (same label, same set of affirmed terms)? Rows are compared as collections; row numbers are
    never aligned."""
    if not lists["bags"]:
        return None
    for label, rows in lists["label_rows"].items():
        if matrix["label_rows"].get(label) != rows:
            return None
    if any(matrix["bags"].get(bag) != n for bag, n in lists["bags"].items()):
        return None
    return {"labels": len(lists["label_rows"]), "rows": sum(lists["label_rows"].values())}


def _says_symptom(heading: str, term: str, file: str, listed: dict[str, str], listed_share: tuple[int, int]) -> str:
    """How the source itself presents a matrix column as a symptom, or ""."""
    lowered = heading.lower()
    for prefix in ("rare_symptom_", "symptom_"):
        if lowered.startswith(prefix):
            return f"column prefix `{prefix}`"
    if term in listed:
        return f"the same archive lists the term in `{listed[term]}`"
    if "symptom" in file.lower():
        return f"file name `{file}`"
    if listed_share[1] and listed_share[0] * 2 >= listed_share[1]:
        return (
            f"it is a column of a matrix of which the same archive lists {listed_share[0]} of {listed_share[1]} "
            "columns as symptoms"
        )
    return ""


def derive(mappings: list[dict[str, Any]], scans: dict[str, dict[str, Any]], files: dict[str, dict[str, Any]]) -> dict:
    """Proposals for every mapping. Pure: `scans` and `files` are keyed by source ID."""
    by_archive: dict[str, list[str]] = {}
    for sid, info in files.items():
        by_archive.setdefault(info["archive"], []).append(sid)
    twins: dict[str, tuple[str, dict[str, int]]] = {}  # matrix source -> (list file, what matched)
    listed_in: dict[str, dict[str, str]] = {sid: {} for sid in files}  # matrix source -> term -> list file
    for sids in by_archive.values():
        for matrix_sid in (s for s in sids if scans[s]["list_column"] is None):
            for list_sid in (s for s in sids if scans[s]["list_column"] is not None):
                column = scans[list_sid]["list_column"]
                if "symptom" in column.lower():
                    for term in scans[list_sid]["listed"]:
                        listed_in[matrix_sid].setdefault(term, f"{files[list_sid]['file']}:{column}")
                match = same_cases(scans[matrix_sid], scans[list_sid])
                if match:
                    twins[matrix_sid] = (files[list_sid]["file"], match)

    def says(mapping: dict[str, Any]) -> str:
        sid, scan = mapping["source_id"], scans[mapping["source_id"]]
        if mapping["column_index"] is None:
            column = scan["list_column"] or ""
            return f"listed in the column `{column}`" if "symptom" in column.lower() else ""
        positions = [m for m in mappings if m["source_id"] == sid and m["column_index"] is not None]
        share = (sum(1 for m in positions if m["term"] in listed_in[sid]), len(positions))
        return _says_symptom(mapping["original_term"], mapping["term"], files[sid]["file"], listed_in[sid], share)

    stated = {m["mapping_id"]: says(m) for m in mappings}
    # Terms that at least two archives present as symptoms: used to recognise a symptom named in a question.
    presenting: dict[str, set[str]] = {}
    for m in mappings:
        if not is_question(m["original_term"]) and stated[m["mapping_id"]]:
            if classify_kind(m["term"], stated[m["mapping_id"]], frozenset()).rule == "stated_by_source":
                presenting.setdefault(readable(m["term"]), set()).add(files[m["source_id"]]["archive"])
    vocabulary = frozenset(term for term, archives in presenting.items() if len(archives) >= 2)

    blocks: dict[str, dict[int, tuple[str, ...]]] = {}
    for sid, scan in scans.items():
        groups: dict[tuple[int, int, int], list[int]] = {}
        for index, signature in scan["signature"].items():
            if signature[0] >= MIN_BLOCK_ROWS and is_question(scan["header"][index]):
                groups.setdefault(signature, []).append(index)
        blocks[sid] = {
            index: tuple(scan["header"][other] for other in members if other != index)
            for members in groups.values()
            if len(members) > 1
            for index in members
        }

    proposals = []
    for m in mappings:
        sid, scan, index = m["source_id"], scans[m["source_id"]], m["column_index"]
        text = m["original_term"] if is_question(m["original_term"]) else m["term"]
        kind = classify_kind(text, stated[m["mapping_id"]], vocabulary)
        affirmed = scan["listed"].get(m["term"], 0) if index is None else scan["affirmed"].get(index, 0)
        always = index is not None and scan["cases"] > 0 and affirmed == scan["cases"]
        zero = classify_zero(
            is_list_term=index is None,
            always_affirmed=always,
            identical_group=blocks[sid].get(index, ()) if index is not None else (),
            describes_a_symptom=kind.rule == "description_of_a_symptom",
            same_cases_as_lists=twins[sid][0] if sid in twins else "",
        )
        meaning = {
            "version": VERSION,
            "status": "proposal, pending review",
            "kind": kind.kind,
            "kind_rule": kind.rule,
            "kind_basis": kind.basis or kind.reason_undecided,
            "zero": zero.zero,
            "zero_rule": zero.rule,
            "zero_basis": zero.basis,
            "one_means": "an answer was recorded" if zero.zero == ZERO_NO_ANSWER else "affirmed",
            "question_cut_off": is_cut_off(m["original_term"]),
            "affirmed_cases": affirmed,
            "cases": scan["cases"],
        }
        proposals.append({**m, "meaning": meaning, "archive": files[sid]["archive"], "file": files[sid]["file"]})

    populations: dict[str, dict[str, Any]] = {}
    for sid, scan in scans.items():
        population: dict[str, Any] = {}
        if scan["age"]:
            unit, basis = propose_age_unit(scan["age"]["minimum"], scan["age"]["maximum"], scan["age"]["whole_numbers"])
            population["age"] = {
                **scan["age"],
                "unit_proposed": unit,
                "unit_basis": basis,
                "unit_status": "proposal, pending review",
            }
        if sid in twins:
            population["same_cases_as"] = {"file": twins[sid][0], **twins[sid][1], "found_by": VERSION}
        if population:
            populations[sid] = population
    kinds: dict[str, set[str]] = {}
    for p in proposals:
        if p["feature_id"]:
            kinds.setdefault(p["feature_id"], set()).add(p["meaning"]["kind"])
    features = {
        fid: (next(iter(found)) if len(found) == 1 and UNDECIDED not in found else "other")
        for fid, found in kinds.items()
    }
    return {
        "proposals": proposals,
        "populations": populations,
        "features": features,
        "kind_conflicts": sorted(fid for fid, found in kinds.items() if len(found - {UNDECIDED}) > 1),
        "vocabulary": len(vocabulary),
        "twins": {files[sid]["file"]: {"list_file": name, **match} for sid, (name, match) in twins.items()},
    }


def derive_meanings(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    release_id: str = RELEASE_ID,
) -> dict[str, Any]:
    """Derive and store the proposals for every case file. Returns them with what changed."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)
    targets = case_files(manifest)
    require_layouts(raw_dir, targets, (DISEASE_HEADERS,))
    files = {source_id(e["archive"], e["file"]): {"archive": e["archive"], "file": e["file"]} for e in targets}
    engine = create_engine(database_url)
    try:
        with _raw_cursor(engine) as cur:
            cur.execute(
                """SELECT m.mapping_id, m.source_id, m.column_index, m.original_term, m.feature_id, m.status::text,
                          m.transformation ->> 'candidate_term'
                   FROM feature_mappings m WHERE m.release_id = %s AND m.source_id = ANY(%s)
                   ORDER BY m.source_id, m.column_index NULLS LAST, m.original_term""",
                (release_id, list(files)),
            )
            mappings = [
                {
                    "mapping_id": mapping_id,
                    "source_id": sid,
                    "column_index": index,
                    "original_term": heading,
                    "feature_id": feature_id,
                    "status": status,
                    "term": candidate or norm_label(heading.replace("_", " ")),
                }
                for mapping_id, sid, index, heading, feature_id, status, candidate in cur.fetchall()
            ]
            archives_with_lists = {e["archive"] for e in targets if e.get("adapter") == "symptom_list"}
            scans = {}
            for entry in targets:
                sid = source_id(entry["archive"], entry["file"])
                terms = {
                    m["column_index"]: m["term"]
                    for m in mappings
                    if m["source_id"] == sid and m["column_index"] is not None
                }
                with zipfile.ZipFile(raw_dir / entry["archive"]) as archive:
                    scans[sid] = scan_file(archive, entry["file"], terms, entry["archive"] in archives_with_lists)
            result = derive(mappings, scans, files)
            changed = {"mappings": 0, "features": 0, "sources": 0, "left_alone_already_reviewed": 0}
            for p in result["proposals"]:
                if p["status"] != "pending":
                    changed["left_alone_already_reviewed"] += 1
                    continue
                meaning, zero = json.dumps(p["meaning"], sort_keys=True), p["meaning"]["zero"]
                cur.execute(
                    """UPDATE feature_mappings
                       SET transformation = jsonb_set(transformation, '{meaning}', %s::jsonb, true), zero_semantics = %s
                       WHERE mapping_id = %s AND status = 'pending'
                         AND (transformation -> 'meaning' IS DISTINCT FROM %s::jsonb OR zero_semantics IS DISTINCT FROM %s)""",
                    (meaning, zero, p["mapping_id"], meaning, zero),
                )
                changed["mappings"] += cur.rowcount
            for feature_id, kind in result["features"].items():
                cur.execute(
                    "UPDATE features SET kind = %s::feature_kind WHERE feature_id = %s AND status = 'pending' "
                    "AND kind <> %s::feature_kind",
                    (kind, feature_id, kind),
                )
                changed["features"] += cur.rowcount
            for sid, population in result["populations"].items():
                value = json.dumps(population, sort_keys=True)
                cur.execute(
                    "UPDATE sources SET population = population || %s::jsonb WHERE source_id = %s "
                    "AND provenance_status = 'pending' AND NOT population @> %s::jsonb",
                    (value, sid, value),
                )
                changed["sources"] += cur.rowcount
            cur.execute(
                """SELECT count(*) FILTER (WHERE m.status <> 'pending'), count(*) FILTER (WHERE m.zero_semantics = 'absent'),
                          count(*) FILTER (WHERE m.transformation ? 'meaning')
                   FROM feature_mappings m WHERE m.release_id = %s AND m.source_id = ANY(%s)""",
                (release_id, list(files)),
            )
            not_pending, absent, with_meaning = cur.fetchone()
            result["stored"] = {"not_pending": not_pending, "zero_as_denial": absent, "with_meaning": with_meaning}
            result["changed"] = changed
            result["sources"] = {sid: f"{info['archive']}/{info['file']}" for sid, info in files.items()}
    finally:
        engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """What must hold after a run. Empty = consistent."""
    diffs = []
    stored, proposals = result["stored"], result["proposals"]
    if stored["zero_as_denial"]:
        diffs.append(f"{stored['zero_as_denial']} mappings say a zero is a denial; no file records a denial")
    if stored["with_meaning"] + result["changed"]["left_alone_already_reviewed"] < len(proposals):
        diffs.append(f"{stored['with_meaning']} of {len(proposals)} mappings carry a proposal")
    for p in proposals:
        meaning = p["meaning"]
        if not meaning["kind_basis"] or not meaning["zero_basis"]:
            diffs.append(f"{p['file']} {p['original_term']}: a proposal has no basis")
    return diffs


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    kinds: Counter[tuple[str, str]] = Counter()
    zeros: Counter[tuple[str, str]] = Counter()
    for p in result["proposals"]:
        name = f"{p['archive'][8:10]} {p['file']}"
        kinds[(name, p["meaning"]["kind"])] += 1
        zeros[(name, p["meaning"]["zero"])] += 1
    return {"kinds": kinds, "zeros": zeros}


def write_review(result: dict[str, Any], out_dir: Path = REVIEW_DIR) -> list[Path]:
    """The proposals as a table for review, and the list of what the data cannot settle."""
    out_dir.mkdir(parents=True, exist_ok=True)
    table = out_dir / "feature_meaning_proposals.csv"
    columns = (
        "kind",
        "kind_rule",
        "kind_basis",
        "zero",
        "zero_rule",
        "zero_basis",
        "one_means",
        "affirmed_cases",
        "cases",
    )
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["archive", "file", "column_index", "original_term", "feature_id", *columns])
        for p in sorted(
            result["proposals"], key=lambda p: (p["archive"], p["file"], p["column_index"] or 10**9, p["term"])
        ):
            index = "" if p["column_index"] is None else p["column_index"]
            writer.writerow(
                [
                    p["archive"],
                    p["file"],
                    index,
                    p["original_term"],
                    p["feature_id"],
                    *(p["meaning"][c] for c in columns),
                ]
            )
    summary = summarise(result)
    names = sorted({name for name, _ in summary["kinds"]})
    lines = [
        "# Feature meanings proposed from the data (M2.7)",
        "",
        "Generated by `uv run python -m feeltriva_ingestion derive-meanings` (rule set "
        f"`{VERSION}`). Do not edit by hand; rerun the command.",
        "",
        "Everything here is a **proposal, pending review**. It is a reading of column headings and of",
        "value patterns in the files. It is not clinical knowledge and nothing is approved. Counts are",
        "counts of rows in files, not patients and not prevalence.",
        "",
        "## Proposed kind, per file",
        "",
        "| File | symptom | history | risk factor | measurement | undecided |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        row = [
            summary["kinds"].get((name, kind), 0)
            for kind in ("symptom", "history", "risk_factor", "measurement", UNDECIDED)
        ]
        lines.append(f"| {name} | " + " | ".join(f"{n:,}" for n in row) + " |")
    lines += [
        "",
        "The kind `sign` is never proposed: no source separates what a person reports from what an",
        "examiner finds. A column that its source presents as a symptom keeps that kind unless its",
        "wording names relatives, the past, a diagnosis, a treatment, an exposure or a measurement.",
        "",
        "## What a zero means, per file",
        "",
        "| File | not recorded | no answer recorded | no evidence either way |",
        "|---|---:|---:|---:|",
    ]
    for name in names:
        row = [summary["zeros"].get((name, zero), 0) for zero in ("not_recorded", "no_answer", "unknown")]
        lines.append(f"| {name} | " + " | ".join(f"{n:,}" for n in row) + " |")
    lines += [
        "",
        "No file contains a recorded denial, so a zero is never proposed to mean one.",
        "",
    ]
    for file, twin in sorted(result["twins"].items()):
        lines.append(
            f"- **Same cases twice.** All {twin['rows']:,} rows of `{twin['list_file']}` ({twin['labels']:,} labels) exist "
            f"one for one in `{file}` with the same label and the same set of affirmed terms. A zero in `{file}` is "
            "therefore a term that was not listed. The two files must be treated as one set of cases when data is "
            "split for training and testing."
        )
    not_binary: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in result["proposals"]:
        if p["meaning"]["zero"] == ZERO_NO_ANSWER:
            not_binary.setdefault((p["archive"], p["original_term"]), []).append(p)
    if not_binary:
        lines += [
            "",
            f"## {len(not_binary)} columns that are not yes/no answers",
            "",
            "For these columns a 1 only says that an answer was recorded. The answer itself is not in the file.",
            "",
            "| File(s) | Column | Affirmed rows / rows | Why |",
            "|---|---|---:|---|",
        ]
        for (_archive, heading), found in not_binary.items():
            affirmed = sum(p["meaning"]["affirmed_cases"] for p in found)
            cases = sum(p["meaning"]["cases"] for p in found)
            lines.append(
                f"| {', '.join(sorted(p['file'] for p in found))} | `{heading}` | {affirmed:,} / {cases:,} | "
                f"{found[0]['meaning']['zero_rule'].replace('_', ' ')} |"
            )
    lines += ["", "## Age unit", "", "| File | Column | Values | Proposed unit | Basis |", "|---|---|---|---|---|"]
    for sid, population in sorted(result["populations"].items(), key=lambda kv: result["sources"][kv[0]]):
        age = population.get("age")
        if age:
            lines.append(
                f"| {result['sources'][sid]} | `{age['column']}` | {age['minimum']:g} to {age['maximum']:g}, "
                f"{age['distinct_values']} distinct | {age['unit_proposed']} | {age['unit_basis']} |"
            )
    undecided = [p for p in result["proposals"] if p["meaning"]["kind"] == UNDECIDED]
    lines += [
        "",
        f"## Undecided: {len({(p['archive'], p['original_term']) for p in undecided})} headings the wording cannot settle "
        f"({len(undecided)} columns)",
        "",
        "These keep the kind `other`. They need a decision by the owner, or the source's full question text.",
        "",
        "| File | Column | Heading as stored | Why undecided |",
        "|---|---:|---|---|",
    ]
    seen = set()
    for p in undecided:
        key = (p["archive"], p["original_term"])
        if key in seen:
            continue
        seen.add(key)
        files_with = sorted({q["file"] for q in undecided if (q["archive"], q["original_term"]) == key})
        lines.append(
            f"| {', '.join(files_with)} | {p['column_index']} | `{p['original_term']}` | {p['meaning']['kind_basis']} |"
        )
    document = out_dir / "feature_meanings.md"
    document.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [table, document]
