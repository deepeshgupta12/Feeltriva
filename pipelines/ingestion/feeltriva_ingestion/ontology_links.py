"""Candidate links from our disease labels and named terms to HPO and MONDO (M2.14).

Every disease candidate and every named symptom, history or exposure term is looked up in both
vocabularies by the rules of `ontologies.py`. A term that carries exactly our name is stored as a
candidate link with review status `pending`; a link that is already stored keeps its row and its
review decision. Nothing else is stored: every other name is written to the review file with
the reason it has no link and the nearest terms.

No gaps: every term of each file is counted in its inventory, and every one of our names has
exactly one recorded outcome per vocabulary. `check` fails the command when either does not hold.

Nothing leaves this machine: both vocabularies are local files. The review file is kept outside
Git and holds no ICD-11 code, so that no table relating ICD-11 to another vocabulary is produced
(decision E56). Identifiers of other vocabularies inside the files are not read (D-T2).

Licence conditions observed: MONDO is CC BY 4.0 (credit in `README.md`); HPO asks for credit, the
version shown, no change to its content, and a statement that the product uses it (`README.md`).
A stored link holds the term's identifier, its label as published and its address, unchanged.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from . import proposals
from .archives import RAW_DIR
from .cases import _raw_cursor
from .ontologies import (
    ABBREVIATION_ONLY,
    EXACT,
    KINDS,
    LABEL,
    LINKED,
    LOOSER_ONLY,
    NEAREST,
    NOT_LINKABLE,
    NOTHING,
    PLAIN_WORD,
    SENTENCE,
    SEVERAL,
    Candidate,
    Outcome,
    Vocabulary,
    load_readings,
    lookup_as_read,
    not_a_name,
    read_vocabulary,
)
from .release import load_supplementary
from .vocabulary import REVIEW_DIR, link_id, plain, query_for, read_subjects, store_links

REVIEW_FILE = "ontology_links.csv"
_SENTENCE = Outcome(SENTENCE, "a question sentence is not a name; it is not looked up")


def _link(
    vocabulary: Vocabulary, looked_up: str, found: Candidate, reading: dict[str, Any] | None = None
) -> dict[str, Any]:
    detail = {
        "query": looked_up,
        "matched_text": found.matched,
        "synonym_type": found.kind,
        "branch": found.branch,
        "note": found.note,
    }
    if reading and reading.get("read_as"):  # the full name a person confirmed was compared, not our label
        detail.update(
            query=query_for(reading["read_as"]),
            our_name=looked_up,
            read_as=reading["read_as"],
            reading_confirmed_by=reading["confirmed_by"],
            reading_confirmed_on=reading["confirmed_on"],
        )
    return {
        "system": vocabulary.system,
        "version": vocabulary.version,
        "code": found.code,
        "title": found.title,
        "uri": found.uri,
        "method": f"exact_{found.how}" if found.how == LABEL else found.how,
        "detail": detail,
    }


def link_ontologies(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    entries: list[dict[str, Any]] | None = None,
    source_ids: list[str] | None = None,
    progress: Callable[[str], None] = lambda _message: None,
    readings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Look up every disease candidate and named feature term in HPO and MONDO; store exact names as pending links.

    entries: the registered files to read (default: those of `specs/supplementary_sources.json`).
    source_ids limits the subjects to those mapped from these sources (used by tests); default all.
    readings: what a named person has confirmed about some labels (default: `specs/confirmed_readings.json`)."""
    readings = load_readings() if readings is None else readings
    entries = [entry for entry in (load_supplementary() if entries is None else entries) if entry.get("kind") in KINDS]
    if not entries:
        raise SystemExit("no HPO or MONDO file is registered in specs/supplementary_sources.json")
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    vocabularies = []
    for entry in entries:
        progress(f"reading {entry['name']}")
        vocabularies.append(read_vocabulary(raw_dir, entry))
    systems = [vocabulary.system for vocabulary in vocabularies]
    engine = create_engine(database_url)
    items: list[dict[str, Any]] = []
    applied: set[str] = set()
    try:
        with _raw_cursor(engine) as cur:  # a short read: the lookups below hold no database transaction open
            subjects = read_subjects(cur, source_ids)
        progress(f"looking up {len(subjects)} items")
        for subject_type, subject_id, name, kind, question in subjects:
            item: dict[str, Any] = {
                "type": subject_type,
                "id": subject_id,
                "name": name,
                "kind": kind,
                "looked_up": "" if question else query_for(name),
                "links": [],
                "outcomes": {},
            }
            reading = None if question else readings.get(item["looked_up"])
            item["read_as"] = str((reading or {}).get("read_as") or "")
            if reading:
                applied.add(item["looked_up"])
            for vocabulary in vocabularies:
                outcome = _SENTENCE if question else lookup_as_read(vocabulary, name, reading)
                item["outcomes"][vocabulary.system] = outcome
                if outcome.link is not None:
                    item["links"].append(_link(vocabulary, item["looked_up"], outcome.link, reading))
            items.append(item)
        with _raw_cursor(engine) as cur:
            inserted = store_links(cur, items)
            # Every name without a link goes before a reviewer with its reason and its near terms (M2.4b).
            unlinked = unlinked_names(items, vocabularies)
            proposed = proposals.store(cur, unlinked, bases=tuple(_BASIS.values()), complete=source_ids is None)
            cur.execute(
                """SELECT system, status::text, count(*), count(*) FILTER (WHERE uri IS NULL OR uri = '' OR title = ''),
                          count(*) FILTER (WHERE status <> 'pending' AND reviewer IS NULL)
                   FROM terminology_links WHERE system = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2""",
                (systems,),
            )
            stored = [(row[0], row[1], row[2], row[3], row[4]) for row in cur.fetchall()]
            cur.execute(
                """WITH n AS (SELECT disease_id, count(*) AS labels FROM case_labels GROUP BY 1),
                        l AS (SELECT disease_id, bool_or(system = ANY(%s)) AS here, bool_or(system <> ALL(%s)) AS elsewhere
                              FROM terminology_links WHERE disease_id IS NOT NULL AND status <> 'rejected' GROUP BY 1)
                   SELECT coalesce(sum(n.labels), 0),
                          coalesce(sum(n.labels) FILTER (WHERE l.here), 0),
                          coalesce(sum(n.labels) FILTER (WHERE l.elsewhere), 0),
                          coalesce(sum(n.labels) FILTER (WHERE l.disease_id IS NOT NULL), 0)
                   FROM n LEFT JOIN l USING (disease_id)""",
                (systems, systems),
            )
            total, here, elsewhere, either = cur.fetchone()
    finally:
        engine.dispose()
    return {
        "vocabularies": vocabularies,
        "items": items,
        "inserted": {system: inserted.get(system, 0) for system in systems},
        "stored": stored,
        "readings": {
            "in_file": len(readings),
            "applied": sorted(applied),
            # A reading that fits none of our names is a slip in the file, unless only some sources were looked at.
            "fit_no_name": [] if source_ids is not None else sorted(set(readings) - applied),
        },
        "case_labels": {
            "all": int(total),
            "label_linked_here": int(here),
            "label_linked_in_another_vocabulary": int(elsewhere),
            "label_linked_anywhere": int(either),
        },
        "proposals": proposed,
        "for_review": proposals.lines(proposed),
        # Each name without a link in a vocabulary must have at least one row there: counted both ways.
        "names_for_review": len({(row["disease_id"] or row["feature_id"], row["system"]) for row in unlinked}),
    }


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    """Counts for the report: per group of items and vocabulary, how many had each outcome."""
    rows: Counter[tuple[str, str, str]] = Counter()
    linked: Counter[tuple[str, str]] = Counter()
    groups: Counter[str] = Counter()
    for item in result["items"]:
        group = "disease labels" if item["type"] == "disease" else "feature terms"
        groups[group] += 1
        for system, outcome in item["outcomes"].items():
            how = outcome.outcome
            if outcome.link is not None and outcome.read_as:
                how = "linked: the full name a person confirmed for our label is a name of the term"
            elif outcome.link is not None:
                how = (
                    "linked: our name is the term's label"
                    if outcome.link.how == LABEL
                    else "linked: our name is an exact synonym"
                )
            rows[(group, system, how.replace("_", " "))] += 1
        if item["links"]:
            linked[(group, "linked in at least one of them")] += 1
        elif item["looked_up"]:
            linked[(group, "looked up, no link in either")] += 1
    return {"rows": rows, "linked": linked, "groups": groups}


def check(result: dict[str, Any]) -> list[str]:
    """Everything that would be a gap or a link that is not a name match; empty when there is none."""
    diffs: list[str] = []
    by_system = {vocabulary.system: vocabulary for vocabulary in result["vocabularies"]}
    for system, vocabulary in by_system.items():
        counted = vocabulary.inventory
        if counted["current"] + counted["obsolete"] != counted["terms"] or counted["terms"] != len(vocabulary.terms):
            diffs.append(f"{system}: current and obsolete terms do not add up to the terms of the file")
        if sum(counted["by_branch"].values()) != counted["current"]:
            diffs.append(f"{system}: the branches do not account for every current term")
        if counted["terms"] + counted["entries_of_other_vocabularies"] != counted["entries_in_file"]:
            diffs.append(f"{system}: the file holds entries that were not counted")
    for item in result["items"]:
        if set(item["outcomes"]) != set(by_system):
            diffs.append(f"{item['name']}: no recorded outcome in {sorted(set(by_system) - set(item['outcomes']))}")
        for system, outcome in item["outcomes"].items():
            vocabulary, found = by_system[system], outcome.link
            if outcome.outcome != LINKED and not outcome.reason:
                diffs.append(f"{item['name']}: {system}: no link and no reason")
            if (outcome.outcome == SENTENCE) != (not item["looked_up"]):
                diffs.append(f"{item['name']}: {system}: a name was skipped, or a sentence was looked up")
            if (found is None) != (outcome.outcome != LINKED):
                diffs.append(f"{item['name']}: {system}: outcome and link disagree")
            if found is not None and (
                found.code not in vocabulary.linkable
                or found.how not in (LABEL, EXACT)
                or not_a_name(found.kind)
                or plain(found.matched) != (query_for(outcome.read_as) if outcome.read_as else item["looked_up"])
                or not found.title
                or not found.uri
            ):
                diffs.append(f"{item['name']}: {system} {found.code} is not a link by an exact name")
    if sum(len(item["links"]) for item in result["items"]) != sum(
        1 for item in result["items"] for outcome in item["outcomes"].values() if outcome.outcome == LINKED
    ):
        diffs.append("the links to store and the linked outcomes differ in number")
    for name in result["readings"]["fit_no_name"]:
        diffs.append(f"the confirmed reading of {name!r} fits none of our names")
    for system, status, _count, incomplete, unsigned in result["stored"]:
        if incomplete:
            diffs.append(f"{incomplete} stored {system} links ({status}) lack a title or an address")
        if unsigned:  # a decided link is expected once review has begun; a decision without a reviewer's name is not
            diffs.append(f"{unsigned} stored {system} links are {status} without a recorded reviewer")
    without_link = sum(
        1 for item in result["items"] for outcome in item["outcomes"].values() if outcome.outcome != LINKED
    )
    if without_link != result["names_for_review"]:
        diffs.append(
            f"{without_link} names have no link in a vocabulary, but {result['names_for_review']} of them were "
            "given a row for review"
        )
    return diffs + proposals.check(result["proposals"])


def write_review(result: dict[str, Any], out_dir: Path = REVIEW_DIR) -> Path:
    """One row per item and vocabulary: its link, or the reason it has none and the nearest terms.

    Kept outside Git. It holds no code of ICD-11 or of any vocabulary other than the one named in the row."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / REVIEW_FILE
    versions = {vocabulary.system: vocabulary.version for vocabulary in result["vocabularies"]}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "type",
                "id",
                "name",
                "kind",
                "looked_up",
                "read_as",
                "system",
                "version",
                "outcome",
                "reason",
                "code",
                "title",
                "uri",
                "match",
                "matched_text",
                "synonym_type",
                "branch",
                "note",
                "candidates",
            ]
        )
        for item in result["items"]:
            for system, outcome in item["outcomes"].items():
                found = outcome.link
                candidates = " | ".join(
                    f"{c.code} {c.title} [{c.how.replace('_', ' ')}"
                    + (f", {c.kind.replace('_', ' ')}" if c.kind else "")
                    + f': "{c.matched}"; {c.branch}'
                    + (f"; {c.note}" if c.note else "")
                    + "]"
                    for c in outcome.candidates
                )
                writer.writerow(
                    [
                        item["type"],
                        item["id"],
                        item["name"],
                        item["kind"],
                        item["looked_up"],
                        outcome.read_as,
                        system,
                        versions[system],
                        outcome.outcome,
                        outcome.reason,
                        *(
                            [
                                found.code,
                                found.title,
                                found.uri,
                                found.how,
                                found.matched,
                                found.kind,
                                found.branch,
                                found.note,
                            ]
                            if found is not None
                            else [""] * 8
                        ),
                        candidates,
                    ]
                )
    return path


# -- the names without a link, for a reviewer (M2.4b) -------------------------------------------------
# Every outcome that is not a link, and the kind of proposal it becomes. An outcome that is not listed here
# stops the command: no name may be left without a row.
_BASIS = {
    ABBREVIATION_ONLY: proposals.ABBREVIATION,
    SEVERAL: proposals.SEVERAL_TERMS,
    LOOSER_ONLY: proposals.LOOSER,
    NEAREST: proposals.NEAREST,
    NOT_LINKABLE: proposals.NOT_LINKABLE,
    PLAIN_WORD: proposals.PLAIN_WORD,
    NOTHING: proposals.NO_TERM,
    SENTENCE: proposals.SENTENCE,
}


def unlinked_names(items: list[dict[str, Any]], vocabularies: list[Vocabulary]) -> list[dict[str, Any]]:
    """For each name and vocabulary without a link: one proposal per term the look-up found near it, or one
    row without a term that records the reason."""
    rows = []
    for item in items:
        for vocabulary in vocabularies:
            outcome = item["outcomes"][vocabulary.system]
            if outcome.outcome == LINKED:
                continue
            basis = _BASIS[outcome.outcome]
            common = {"looked_up": item["looked_up"], "read_as": item["read_as"]}
            if not outcome.candidates:
                rows.append(
                    proposals.row(
                        item, vocabulary.system, vocabulary.version, basis, outcome.reason, None, None, **common
                    )
                )
            for found in outcome.candidates:
                rows.append(
                    proposals.row(
                        item,
                        vocabulary.system,
                        vocabulary.version,
                        basis,
                        outcome.reason,
                        {"code": found.code, "title": found.title, "uri": found.uri},
                        link_id(item["id"], vocabulary.system, vocabulary.version, found.code),
                        matched_text=found.matched,
                        how=found.how,
                        synonym_type=found.kind,
                        branch=found.branch,
                        note=found.note,
                        **common,
                    )
                )
    return rows
