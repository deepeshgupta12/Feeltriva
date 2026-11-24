"""The ingestion completeness report, one group of checks per mapping-table row (M1.13).

`emit` turns what `completeness.gather` measured into report lines. Each line belongs to a row
of the source-to-target table in `docs/04_DATA_MAPPING.md` (T1 ... T27) or, as row 0, to the M1
acceptance criteria of `docs/05_IMPLEMENTATION_BACKLOG.md`. The rows about case files are in
`completeness_cases`; this module has the rows about all files, the narrative tables, the text
files and the acceptance criteria. It only compares numbers: it reads neither the database nor
the archives.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from .chunks import CATEGORY_FLAG, TEXT_ARCHIVE
from .completeness_cases import (
    TEXT_ROW,
    TEXT_STATEMENTS,
    case_file_rows,
    disease_mapping_rows,
    name_of,
    roles_of,
    row_diffs,
    split_rows,
)
from .decisions import IN_ORDER

if TYPE_CHECKING:
    from .completeness import Report


def _all_files(report: Report, world: dict[str, Any]) -> None:
    manifest, reference, files, stores = world["manifest"], world["reference"], world["files"], world["archives"]
    report.check(
        1,
        "archives registered with the manifest's SHA-256, their size and a verification time",
        len(manifest.archives),
        stores["registered"],
        "manifest",
    )
    report.check(
        1,
        "archives whose stored bytes, re-read from the object store now, hash to the manifest's SHA-256"
        + (f" ({stores['problem']})" if stores["problem"] else ""),
        len(manifest.archives),
        stores["stored"],
        "manifest",
    )
    versions = 0
    for key, info in files.items():
        stored = reference["sources"].get(info["sid"])
        versions += (
            stored is not None and stored[0] == manifest.archives[key[0]][:16] and stored[1] == info["member_sha256"]
        )
    text = reference["sources"].get(world["text_sid"])
    versions += text is not None and text[1] == manifest.archives[TEXT_ARCHIVE]
    report.check(
        1,
        "source versions carrying the archive version and the file's SHA-256 (CSV files + the text-file set)",
        len(files) + 1,
        versions,
        "manifest + files",
    )
    in_order = 0
    for key, info in files.items():
        entry, facts = info["entry"], info["facts"]
        rows, distinct, numbers, first, last, no_locator = reference["records"].get(
            info["sid"], (0, 0, 0, None, None, 0)
        )
        report.check(
            1,
            f"{name_of(key)}: columns / row records / exact-unique rows",
            f"{entry['expected_columns']:,} / {entry['expected_rows']:,} / {entry['exact_unique_rows']:,}",
            f"{len(info['header']):,} / {rows:,} / {distinct:,}",
            "manifest",
        )
        in_order += bool(
            facts and facts["aligned"] and rows == numbers == last and first == 1 and not no_locator and rows > 0
        )
    report.check(
        1, "files whose records are numbered 1..N in file order, each with a row locator", len(files), in_order, "files"
    )
    compared = [info["facts"] for info in files.values() if info["facts"]]
    report.check(
        1,
        "rows whose stored content hash differs from the file",
        0,
        sum(facts["row_diffs"]["content hash"] for facts in compared),
        "files",
    )
    report.check(
        1,
        "malformed rows kept as flagged records without a case",
        sum(audit["malformed_rows"] for audit in world["audit_files"].values()),
        sum(facts["flags"]["malformed_row"] for facts in compared),
        "audit.json",
    )
    report.check(
        1,
        "columns that have a target (a feature mapping or a named field)",
        sum(info["entry"]["expected_columns"] for info in files.values()),
        sum(info["columns_with_a_target"] for info in files.values()),
        "manifest",
    )
    texts = world["texts"]
    report.check(
        1,
        "text files registered as records with the file's SHA-256",
        texts["files"],
        texts["records_with_file_digest"],
        "manifest",
    )
    report.check(
        1,
        "whole-file provenance records (one per case file, for per-file aggregates)",
        sum(1 for info in files.values() if info["kind"] == "case"),
        world["whole_file_records"],
        "files",
    )


def _statement_file(report: Report, world: dict[str, Any], key: tuple[str, str], info: dict[str, Any]) -> None:
    roles, facts, sid = roles_of(info["entry"]), info["facts"], info["sid"]
    if facts is None:
        for row in sorted(set(roles.values())):
            report.check(row, f"{name_of(key)}: layout", "as registered", "differs (source schema drift)", "manifest")
        return
    disease_mapping_rows(report, world, key, sid, roles["mappings"])
    row = roles["statement"]
    linked, attributed = facts["links_expected"], facts["attribution_rows"]
    report.check(row, "rows with text, each linked to exactly one statement", linked, facts["links"], "file")
    report.check(
        row,
        "distinct statements (same text for one disease is one statement, all attributions kept)",
        facts["statements_expected"],
        facts["statements"],
        "file",
    )
    detail, differing = row_diffs(facts)
    report.check(row, f"rows whose stored statement or attribution differs from the file{detail}", 0, differing, "file")
    report.check(row, "statements linked to the source URL supplied for them", linked, attributed["source_url"], "file")
    report.check(
        row,
        "statements whose status was changed by no reviewer (imported text stays pending until reviewed)",
        0,
        facts["changed_by_no_reviewer"],
        "rule",
    )
    if "native_id" in roles:
        stored = world["reference"]["disease"].get(sid, {})
        report.check(
            roles["native_id"],
            "disease names mapped with their native ID, scoped to this source",
            len(world["main_rows"]),
            sum(
                1 for main in world["main_rows"] if stored.get(main.get("name", ""), (None, None))[1] == main.get("id")
            ),
            "file",
        )
    if "category" in roles:
        row, texts = roles["category"], world["texts"]
        report.check(
            row,
            "rows whose category is kept as supplied beside the statement",
            linked,
            attributed["source_category"],
            "file",
        )
        report.check(
            row,
            "rows queued for review of the category (not an approved taxonomy)",
            facts["rows"],
            facts["flags"][CATEGORY_FLAG],
            "file",
        )
        report.check(
            row,
            "text chunks carrying the unreviewed category as supplied",
            texts["chunks"],
            texts["with_source_category"],
            "file",
        )
    if "attributes" in roles:
        row = roles["attributes"]
        report.check(
            row, "rows whose word count is kept as a source attribute", linked, attributed["word_count"], "file"
        )
        report.check(
            row, "rows whose URL is kept as the statement's source URL", linked, attributed["source_url"], "file"
        )
    if "join" in roles:
        for flag in ("unknown_native_disease_id", "disease_name_disagrees_with_diseases_main"):
            report.check(
                roles["join"], f"rows flagged {flag}", facts["expected_flags"][flag], facts["flags"][flag], "file"
            )
        report.check(
            roles["join"], "rows joined to the disease table by native ID", linked, attributed["native_id"], "file"
        )
    evidence = world["evidence"]
    if "evidence" in roles:
        row = roles["evidence"]
        report.check(
            row,
            "proposed disease-feature evidence: feature terms mentioned in a statement (a mention is not an assertion)",
            evidence["mentions_expected"],
            evidence["mentions"],
            "stored statements, recomputed",
        )
        report.check(
            row,
            "proposals that are not a mention in the statement, or whose status was changed by no reviewer",
            0,
            evidence["mentions_unexpected"] + evidence["mentions_changed_by_no_reviewer"],
            "rule",
        )
        claims = world["claims"]
        report.check(
            row,
            "single claims of the symptom statements, each a span of its statement, in the review queue",
            claims["expected"],
            claims["stored_as_expected"],
            "stored statements, recomputed",
        )
        report.check(
            row,
            "claims that are not their statement's text, are not made by the rules, or were decided by no reviewer",
            0,
            claims["not_their_text"] + claims["unexpected"] + claims["decided_without_reviewer"],
            "rule",
        )
    if "no_evidence" in roles:
        report.check(
            roles["no_evidence"],
            "evidence proposals derived from a treatment statement (a mention is never a cure or eligibility)",
            0,
            evidence["by_statement_type"].get("treatment", 0),
            "rule",
        )
    if "provenance" in roles:
        for field, column in (
            ("source", "Source"),
            ("source_url", "Source_URL"),
            ("retrieved_date", "Retrieved_Date"),
            ("canonical_query", "Canonical_Query"),
        ):
            report.check(
                roles["provenance"], f"rows whose `{column}` is retained as supplied", linked, attributed[field], "file"
            )


def _texts(report: Report, world: dict[str, Any]) -> None:
    texts = world["texts"]
    row = TEXT_ROW
    report.check(
        row,
        "text files registered as records with the file's SHA-256",
        texts["files"],
        texts["records_with_file_digest"],
        "manifest",
    )
    report.check(
        row, "text files that could not be read as Disease / Category / URL + body", 0, texts["unreadable"], "files"
    )
    report.check(row, "chunks stored", texts["chunks_expected"], texts["chunks"], "files, re-chunked")
    report.check(
        row,
        "chunks whose stored character offsets reproduce their text from the file",
        texts["chunks"],
        texts["offsets_reproduce_text"],
        "files",
    )
    report.check(
        row,
        "chunks carrying URL, disease label, document SHA-256 and extraction version",
        texts["chunks"],
        texts["with_attribution"],
        "files",
    )
    report.check(row, "body characters that are in no chunk", 0, texts["uncovered_characters"], "files")
    report.check(
        row,
        "documents with chunks / chunks searchable by full text",
        f"{texts['files']:,} / {texts['chunks']:,}",
        f"{texts['documents_with_chunks']:,} / {texts['searchable']:,}",
        "files",
    )
    report.check(
        row,
        "status of the knowledge release holding the chunks (never served before review)",
        "pending",
        texts["release_status"],
        "rule",
    )
    report.later(
        row,
        "statements extracted from the text files after review",
        f"{world['text_statements']} statements",
        TEXT_STATEMENTS,
    )


def _acceptance(report: Report, world: dict[str, Any]) -> None:
    files, reference, evidence = world["files"], world["reference"], world["evidence"]
    cases = {key: info for key, info in files.items() if info["kind"] == "case" and info["facts"]}
    texts = world["texts"]
    report.check(
        0,
        "CSV files / text files accounted for",
        f"{len(world['manifest'].files)} / {texts['files']}",
        f"{sum(1 for info in files.values() if info['facts'] and info['facts']['aligned'])} / {texts['records_with_file_digest']}",
        "manifest",
    )
    repeated = {key: info["facts"]["cases"] - len(info["facts"]["stored_pairs"]) for key, info in cases.items()}
    wanted = {key: world["audit_files"][key]["repeated_profiles_excluding_patient_id"] for key in cases}
    report.check(
        0,
        "repeated feature profiles (label included) over the case files / files equal to the audit",
        f"{sum(wanted.values()):,} / {len(wanted)}",
        f"{sum(repeated.values()):,} / {sum(1 for key in cases if repeated[key] == wanted[key])}",
        "audit.json",
    )
    report.check(
        0,
        "rows in exact-duplicate groups, marked as such on the case",
        sum(info["facts"]["rows_in_exact_duplicate_groups"] for info in cases.values()),
        sum(info["facts"]["duplicate_status"]["exact_duplicate_row"] for info in cases.values()),
        "files",
    )
    report.check(
        0,
        "cases without a duplicate status, or whose equal profiles do not share one cluster ID",
        0,
        sum(info["facts"]["duplicate_status"][None] + info["facts"]["cluster_diffs"] for info in cases.values()),
        "files",
    )
    by_archive: dict[str, set[str]] = {}
    for key, info in files.items():
        by_archive.setdefault(key[0], set()).update(m[0] for m in reference["disease"].get(info["sid"], {}).values())
    report.check(
        0,
        "lexical disease candidates referenced by the label mappings",
        world["audit"]["union_lexical_disease_labels"],
        len(set().union(*by_archive.values())) if by_archive else 0,
        "audit.json",
    )
    overlap = world["audit"]["overlap"]
    report.check(
        0,
        "archive pairs whose number of shared lexical labels equals the audit",
        len(overlap),
        sum(
            1
            for pair in overlap
            if len(by_archive.get(pair["archive_a"], set()) & by_archive.get(pair["archive_b"], set()))
            == pair["shared_lexical_labels"]
        ),
        "audit.json",
    )
    pairs_expected = pairs_loaded = wrong = 0
    for key, info in cases.items():
        facts, stored = info["facts"], evidence["cooccurrence"][key]
        expected = {(d, f): n for d, counter in facts["cooccurrence"].items() for f, n in counter.items() if n > 0}
        pairs_expected += len(expected)
        pairs_loaded += len(stored)
        wrong += len(set(stored) - set(expected))
        for pair, n in expected.items():
            found, denominator = stored.get(pair), facts["label_cases"][pair[0]]
            if (
                found is None
                or found[0] != n
                or found[1] != denominator
                or abs(float(found[2]) - n / denominator) > 6e-7
                or found[3] not in IN_ORDER
            ):
                wrong += 1
    report.check(
        0,
        "per-file co-occurrence proposals: label-feature pairs with at least one affirming case",
        pairs_expected,
        pairs_loaded,
        "files",
    )
    report.check(
        0,
        "co-occurrence proposals whose count, denominator or frequency differs from the files, or whose status was "
        "changed by no reviewer",
        0,
        wrong,
        "files",
    )
    mappings = [
        m for group in (reference["positional"], reference["listed"]) for s in group.values() for m in s.values()
    ]
    used = {mapping["feature"] for mapping in mappings}
    # A row a reviewer decided is in order. The two working sets are not decided at all: they stay pending,
    # and what is approved in them is what a published release says (decisions E83, E84).
    changed = {
        "sources": sum(
            1 for info in files.values() if reference["sources"].get(info["sid"], (0, 0, "pending"))[2] not in IN_ORDER
        ),
        "disease mappings": sum(1 for s in reference["disease"].values() for m in s.values() if m[3] not in IN_ORDER),
        "diseases": reference["diseases_changed_by_no_reviewer"],
        "feature mappings": sum(1 for mapping in mappings if mapping["status"] not in IN_ORDER),
        "features": sum(
            1 for feature_id in used if reference["features"].get(feature_id, ("", "pending"))[1] not in IN_ORDER
        ),
        "statements": sum(
            info["facts"]["changed_by_no_reviewer"]
            for info in files.values()
            if info["kind"] == "statement" and info["facts"]
        ),
        "narrative proposals": evidence["mentions_changed_by_no_reviewer"],
        "mapping release": int(reference["mapping_release_status"] != "pending"),
        "knowledge release": int(texts["release_status"] != "pending"),
    }
    found = {name: n for name, n in changed.items() if n}
    report.check(
        0,
        "imported items whose status was changed by no reviewer; only a reviewer may decide"
        f"{' ' + str(found) if found else ''}",
        0,
        sum(changed.values()),
        "rule",
    )
    report.check(
        0,
        "case labels whose origin is recorded as anything but unknown (the files do not say how labels were assigned)",
        0,
        sum(n for info in cases.values() for origin, n in info["facts"]["label_origin"].items() if origin != "unknown"),
        "rule",
    )


class _Named:
    """Puts the file name in front of every line, for rows of the table that cover several files."""

    def __init__(self, report: Report, name: str) -> None:
        self._report, self._name, self.table = report, name, report.table

    def check(self, row: int, measure: str, expected: Any, loaded: Any, basis: str) -> None:
        self._report.check(row, f"{self._name}: {measure}", expected, loaded, basis)

    def later(self, row: int, measure: str, loaded: Any, owner: str) -> None:
        self._report.later(row, f"{self._name}: {measure}", loaded, owner)


def emit(report: Report, world: dict[str, Any]) -> None:
    _all_files(report, world)
    sharing = Counter(id(roles_of(info["entry"])) for info in world["files"].values())
    for key, info in world["files"].items():
        several = sharing[id(roles_of(info["entry"]))] > 1
        target: Any = _Named(report, key[1]) if several else report
        if info["kind"] == "case":
            case_file_rows(target, world, key, info)
        else:
            _statement_file(target, world, key, info)
    _texts(report, world)
    split_rows(report, world)
    _acceptance(report, world)
