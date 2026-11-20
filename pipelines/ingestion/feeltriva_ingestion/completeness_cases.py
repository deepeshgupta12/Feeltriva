"""Completeness checks for the case files (M1.13): labels, patient fields, feature columns,
symptom lists, declared counts and the original split.

Each line belongs to a row of the source-to-target table in `docs/04_DATA_MAPPING.md`. This
module only compares numbers that `completeness.gather` measured: it reads neither the database
nor the archives.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any

from .cases import SPLIT_FLAG
from .lists import COUNT_FLAG, EMPTY_FLAG, feature_candidate_id
from .load import disease_candidate_id

if TYPE_CHECKING:
    from .completeness import Report

A11, A12, A13, A14, A15, A16 = (f"archive({number}).zip" for number in range(11, 17))
NO_ROWS = {
    "rows": 0,
    "present": 0,
    "conflict": 0,
    "zero_outside": 0,
    "absent": 0,
    "not_asked": 0,
    "uncertain_outside": 0,
    "foreign": 0,
}
# Which row of the mapping table speaks about which part of which file.
ROLE_ROWS: dict[tuple[str, str], dict[str, int]] = {
    (A11, "positional_feature_matrix"): {"label": 2, "features": 3},
    (A12, "positional_feature_matrix"): {"label": 4, "features": 5},
    (A12, "symptom_list"): {"label": 6, "list": 6},
    (A13, "diseases_main.csv"): {"mappings": 7, "native_id": 7, "category": 8, "statement": 9, "attributes": 10},
    (A13, "causes.csv"): {"mappings": 11, "statement": 11, "join": 11},
    (A13, "symptoms.csv"): {"mappings": 12, "statement": 12, "join": 12, "evidence": 12},
    (A13, "treatments.csv"): {"mappings": 13, "statement": 13, "join": 13, "no_evidence": 13},
    (A14, "symptom_list"): {
        "patient_id": 15,
        "age": 16,
        "demographic": 17,
        "list": 18,
        "declared_count": 19,
        "label": 20,
    },
    (A15, "positional_feature_matrix"): {
        "patient_id": 21,
        "age": 21,
        "demographic": 21,
        "label": 21,
        "split": 21,
        "features": 22,
        "declared_count": 23,
    },
    (A16, "positional_feature_matrix"): {"label": 24, "features": 25},
    (A16, "disease_description"): {"mappings": 26, "statement": 26, "provenance": 27},
}
TEXT_ROW = 14
# The single claims of the statements are checked since M2.6. Statements from the text files come after
# the chunks have been reviewed, which the approval workflow owns.
TEXT_STATEMENTS = "the review of the text chunks (M2.5)"
# M2.7 stored proposals; what is left is the owner's review of them and the approval workflow.
FEATURE_MEANINGS = "the owner's review of the M2.7 proposals (approval: M2.5)"


def roles_of(entry: dict[str, Any]) -> dict[str, int]:
    by_file = ROLE_ROWS.get((entry["archive"], entry["file"]))
    return by_file if by_file is not None else ROLE_ROWS.get((entry["archive"], entry.get("adapter", "")), {})


def name_of(key: tuple[str, str]) -> str:
    file = key[1] if len(key[1]) <= 36 else key[1][:33] + "..."
    return f"{key[0][8:10]} {file}"


def row_diffs(facts: dict[str, Any]) -> tuple[str, Any]:
    """(detail for the label, loaded value) for 'rows that differ from the file'."""
    if not facts["aligned"]:
        return "", "the stored records do not pair with the file's rows"
    diffs = {name: n for name, n in facts["row_diffs"].items() if n}
    if facts.get("extra_label_rows"):
        diffs["more than one label"] = facts["extra_label_rows"]
    return (f" {diffs}" if diffs else ""), sum(diffs.values())


def disease_mapping_rows(report: Report, world: dict[str, Any], key: tuple[str, str], sid: str, row: int) -> None:
    cross = world["disease_cross"].get(key, {})
    stored = world["reference"]["disease"].get(sid, {})
    same = sum(1 for label, candidate in cross.items() if stored.get(label, (None,))[0] == candidate)
    report.check(
        row,
        "label spellings mapped exactly as in the crosswalk",
        len(cross),
        same if len(stored) == len(cross) else f"{same} of {len(stored)} stored",
        "crosswalk",
    )
    lexical = sum(
        1
        for label, (disease_id, _native, method, status) in stored.items()
        if disease_id == disease_candidate_id(label) and method == "lexical_casefold_whitespace" and status == "pending"
    )
    report.check(row, "label mappings that are lexical candidates awaiting review", len(stored), lexical, "rule")


def _features(report: Report, world: dict[str, Any], key: tuple[str, str], info: dict[str, Any], row: int) -> None:
    facts, audit = info["facts"], world["audit_files"][key]
    mapped = world["reference"]["positional"].get(info["sid"], {})
    cross = world["feature_cross"].get(key, {})
    stored = {index: world["feature_rows"].get(mapping["id"], NO_ROWS) for index, mapping in mapped.items()}
    same = sum(
        1
        for index, (heading, candidate) in cross.items()
        if index in mapped and mapped[index]["term"] == heading and mapped[index]["feature"] == candidate
    )
    report.check(
        row,
        "column positions mapped exactly as in the crosswalk (position, heading, candidate)",
        len(cross),
        same if len(mapped) == len(cross) else f"{same} of {len(mapped)} stored",
        "crosswalk",
    )
    stated = re.search(r"(\d+) (?:columns|positions)", report.table[row - 1][0]) if row <= len(report.table) else None
    if stated:
        report.check(row, "feature positions named in the mapping table", int(stated.group(1)), len(mapped), "docs/04")
    report.check(
        row, "headings found at their registered position in the file", len(mapped), info["headings_in_place"], "file"
    )
    report.check(
        row,
        "feature values stored (every non-zero cell; both sides of a conflict)",
        sum(facts["column_rows"][index] for index in mapped),
        sum(counts["rows"] for counts in stored.values()),
        "file",
    )
    report.check(
        row,
        "columns whose stored and affirmed counts both equal the file",
        len(mapped),
        sum(
            1
            for index, counts in stored.items()
            if counts["rows"] == facts["column_rows"][index] and counts["present"] == facts["column_present"][index]
        ),
        "file",
    )
    report.check(
        row,
        "blank cells kept as not_asked / other values kept as uncertain",
        f"{facts['blank_cells']:,} / {facts['other_value_cells']:,}",
        f"{sum(c['not_asked'] for c in stored.values()):,} / {sum(c['uncertain_outside'] for c in stored.values()):,}",
        "file",
    )
    report.check(
        row,
        "zero cells stored outside a conflict, or values marked absent (an imported zero is never a denial)",
        0,
        sum(counts["zero_outside"] + counts["absent"] for counts in stored.values()),
        "rule",
    )
    report.check(
        row,
        "mappings still pending review, none reading a zero as a denial",
        len(mapped),
        sum(1 for mapping in mapped.values() if mapping["zero"] != "absent" and mapping["status"] == "pending"),
        "manifest",
    )
    report.check(
        row,
        "feature values attached to a case of another source file",
        0,
        sum(counts["foreign"] for counts in stored.values()),
        "rule",
    )
    headings = Counter(mapping["term"] for mapping in mapped.values())
    repeated = {heading for heading, n in headings.items() if n > 1}
    if repeated or audit["duplicate_header_count"]:
        conflicts = audit["duplicate_column_disagreement_rows"]
        report.check(
            row,
            "repeated headings kept as separate positions",
            audit["duplicate_header_count"],
            len(repeated),
            "audit.json",
        )
        report.check(
            row,
            "repeated headings whose number of conflicting cases equals the audit",
            len(conflicts),
            sum(
                1
                for heading, n in conflicts.items()
                if heading in repeated
                and all(
                    stored[index]["conflict"] == n for index, mapping in mapped.items() if mapping["term"] == heading
                )
            ),
            "audit.json",
        )
        report.check(
            row,
            "conflict rows stored (every position of a conflicting heading, zeros included)",
            facts["conflict_rows"],
            sum(counts["conflict"] for counts in stored.values()),
            "file",
        )
    if row <= len(report.table) and "classify" in report.table[row - 1][2]:
        kinds = world["reference"]["features"]
        classified = sum(1 for mapping in mapped.values() if kinds.get(mapping["feature"], ("other",))[0] != "other")
        report.later(
            row,
            "feature positions classified as symptom, history, risk, measurement or other",
            f"{classified} of {len(mapped)} have a proposed kind; none is approved",
            FEATURE_MEANINGS,
        )


def _list(report: Report, world: dict[str, Any], info: dict[str, Any], row: int) -> None:
    facts = info["facts"]
    listed = world["reference"]["listed"].get(info["sid"], {})
    terms = facts["term_cases"]
    stored = {term: world["feature_rows"].get(mapping["id"], NO_ROWS) for term, mapping in listed.items()}
    report.check(
        row,
        "distinct list terms, each with its own pending mapping (and no mapping for other terms)",
        len(terms),
        sum(1 for term in terms if term in listed and listed[term]["status"] == "pending")
        if set(listed) <= set(terms)
        else f"{len(set(listed) - set(terms))} mappings for terms the file does not contain",
        "file",
    )
    report.check(
        row,
        "list terms whose candidate follows the lexical rule",
        len(listed),
        sum(1 for term, mapping in listed.items() if mapping["feature"] == feature_candidate_id(term)),
        "rule",
    )
    report.check(
        row,
        "listed items stored (one per distinct term per case)",
        sum(terms.values()),
        sum(counts["rows"] for counts in stored.values()),
        "file",
    )
    report.check(
        row,
        "terms whose stored count equals the file",
        len(terms),
        sum(1 for term, n in terms.items() if term in stored and stored[term]["rows"] == n == stored[term]["present"]),
        "file",
    )
    report.check(
        row,
        "values marked absent (an unlisted symptom is unknown, never a denial)",
        0,
        sum(counts["absent"] for counts in stored.values()),
        "rule",
    )
    report.check(
        row, "rows with an empty list, flagged on the record", facts["empty_lists"], facts["flags"][EMPTY_FLAG], "file"
    )
    report.check(
        row,
        "listed items attached to a case of another source file",
        0,
        sum(counts["foreign"] for counts in stored.values()),
        "rule",
    )


def case_file_rows(report: Report, world: dict[str, Any], key: tuple[str, str], info: dict[str, Any]) -> None:
    roles, facts, sid = roles_of(info["entry"]), info["facts"], info["sid"]
    if facts is None:
        for row in sorted(set(roles.values())):
            report.check(row, f"{name_of(key)}: layout", "as registered", "differs (source schema drift)", "manifest")
        return
    audit = world["audit_files"][key]
    cases = facts["rows"] - facts["malformed"]
    diffs = facts["row_diffs"]
    row = roles["label"]
    disease_mapping_rows(report, world, key, sid, row)
    stored_mappings = world["reference"]["disease"].get(sid, {})
    report.check(
        row,
        "distinct label spellings on the loaded cases",
        audit["disease_labels"],
        len(facts["stored_labels"]),
        "audit.json",
    )
    report.check(
        row,
        "case labels with no mapping in the crosswalk",
        0,
        len(facts["stored_labels"] - set(stored_mappings)),
        "rule",
    )
    report.check(
        row,
        "cases whose label and lexical candidate equal the file",
        cases,
        facts["cases"] - diffs["label or its lexical candidate"],
        "file",
    )
    detail, differing = row_diffs(facts)
    report.check(
        row, f"rows whose stored record or case differs from the file in any field{detail}", 0, differing, "file"
    )
    if "patient_id" in roles:
        report.check(
            roles["patient_id"],
            "cases whose source patient ID equals the file",
            cases,
            facts["cases"] - diffs["patient id"],
            "file",
        )
    if "age" in roles:
        row = roles["age"]
        report.check(row, "cases whose age value equals the file", cases, facts["cases"] - diffs["age"], "file")
        report.check(
            row,
            "ages that are not a number, kept empty and flagged",
            facts["age_not_parsed"],
            facts["flags"]["age_not_parsed"],
            "file",
        )
        report.check(
            row,
            "cases with an age unit set (no source documentation confirms the unit)",
            0,
            facts["age_unit_set"],
            "rule",
        )
        report.later(
            row, "age unit confirmed from source documentation", "not confirmed; unit left empty", FEATURE_MEANINGS
        )
    if "demographic" in roles:
        row = roles["demographic"]
        report.check(
            row,
            "cases whose demographic field name and value are kept as supplied",
            cases,
            facts["cases"] - diffs["demographic field or value"],
            "file",
        )
        report.check(
            row,
            "value counts (sample counts of rows, not prevalence)",
            dict(sorted(audit["sex_counts"].items())),
            dict(sorted(facts["stored_demographic"].items())),
            "audit.json",
        )
    if "split" in roles:
        report.check(
            roles["split"],
            "cases carrying their original split, namespaced by archive",
            cases,
            facts["cases"] - diffs["split"],
            "file",
        )
    if "features" in roles:
        _features(report, world, key, info, roles["features"])
    if "list" in roles:
        _list(report, world, info, roles["list"])
    if "declared_count" in roles:
        row = roles["declared_count"]
        mapped = world["reference"]["positional"].get(sid, {})
        listed = world["reference"]["listed"].get(sid, {})
        report.check(
            row,
            "rows whose declared count differs from the parsed values, flagged on the record",
            facts["declared_count_mismatches"],
            facts["flags"][COUNT_FLAG],
            "file",
        )
        report.check(
            row,
            "declared count registered as a feature (it is a derived count, not ground truth)",
            0,
            sum(1 for mapping in [*mapped.values(), *listed.values()] if mapping["term"].lower() == "symptom_count"),
            "rule",
        )


def split_rows(report: Report, world: dict[str, Any]) -> None:
    """Files of one archive that carry an original split (archive 15 train/test)."""
    by_archive: dict[str, list[dict[str, Any]]] = {}
    for key, info in world["files"].items():
        if info["kind"] == "case" and info["facts"] and "split" in roles_of(info["entry"]):
            by_archive.setdefault(key[0], []).append(info)
    for members in by_archive.values():
        if len(members) < 2:
            continue
        row = roles_of(members[0]["entry"])["split"]
        pairs = [info["facts"]["stored_pairs"] for info in members]
        keys = [info["facts"]["profile_rows"] for info in members]
        shared_keys = {key for key, n in Counter(k for counter in keys for k in counter).items() if n > 1}
        report.check(
            row,
            "feature profiles (label included) present in more than one original split",
            world["audit"]["archive15_train_test_shared_profiles_excluding_patient_id"],
            sum(1 for n in Counter(p for group in pairs for p in group).values() if n > 1),
            "audit.json",
        )
        report.check(
            row,
            "rows flagged as sharing a feature profile across the original split (a leakage warning)",
            sum(counter[key] for counter in keys for key in shared_keys),
            sum(info["facts"]["flags"][SPLIT_FLAG] for info in members),
            "files",
        )
