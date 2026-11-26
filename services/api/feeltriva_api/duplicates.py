"""Duplicates in the stored data: what is counted, and what a rule can settle (M2.18).

Three different things look like "the same thing twice", and they are treated differently.

1. Rows that differ only by the data file they came from. A condition name is stored once per
   file that names it, and a counted fact once per file that counts it. These are not duplicates:
   each row has its own source. The screens show the file, so that the rows can be told apart.
2. Two names for one condition. The pairs come from the suggestions of M2.8 (`relation_suggestions`,
   relation `possible_synonym`): the same words with other punctuation ("common cold",
   "common_cold"), or two names matched to the same entry of a reference list ("heart attack",
   "myocardial infarction"). `condition_groups` puts such names together; `merge_groups` merges
   each group with the service's own merge, so nothing is deleted and every merge can be taken
   out again. A pair listed in `specs/merge_exceptions.json` is not merged, and neither is a group
   whose names are matched to more than one entry: those need a person.
3. The same text stored twice for one condition. `duplicate_texts` finds them once the names are
   merged; `retire_duplicate_texts` keeps the first and retires the copies, each with a note that
   names the text it is a copy of.

The name kept for a merged condition is the standard one (owner's rule E62): the title of the
entry both names are matched to, when there is one; otherwise the spelling without underscores
that the most data files use. Every other name is kept as another name of the condition.

Symptoms and other items have the same kind of duplicates, but the service can only merge
conditions. They are counted here and not changed.

    uv run python -m feeltriva_api.duplicates                        # count; change nothing
    uv run python -m feeltriva_api.duplicates --merge --reviewer NAME --note "..."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from . import disease_merges, review_bulk
from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import (
    Disease,
    DiseaseFeatureEvidence,
    DiseaseMapping,
    Feature,
    RelationSuggestion,
    Statement,
    TerminologyLink,
)
from .settings import get_settings

EXCEPTIONS_PATH = Path(__file__).resolve().parents[3] / "specs" / "merge_exceptions.json"
SAME_CODE, SYNONYM = "same_standard_code", "possible_synonym"


def plain(name: str) -> str:
    """A name as lower-case words: case, underscores, hyphens and punctuation do not count."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def load_exceptions(path: Path = EXCEPTIONS_PATH) -> list[dict[str, Any]]:
    """The pairs of names that are not merged by rule, each with its reason. A file that is unclear is refused."""
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))["not_merged"]
    for entry in entries:
        if len(entry.get("names", [])) != 2 or not entry.get("reason") or not entry.get("noted_on"):
            raise ValueError(f"{path.name}: an exception needs two names, a reason and a date: {entry}")
    return list(entries)


def _same_spelling(tx: Any, model: Any, key: Any, live: Any) -> list[list[str]]:
    """Groups of names of one table that are equal as plain words."""
    groups: dict[str, list[str]] = {}
    for _row_id, name in tx.execute(select(key, model.preferred_name).where(live)).all():
        groups.setdefault(plain(name), []).append(name)
    return sorted(sorted(names) for names in groups.values() if len(names) > 1)


def report(db: Database) -> dict[str, Any]:
    """What looks like a duplicate, counted by kind. Reads only."""
    with db.transaction(None, role="migration") as tx:
        mappings = tx.execute(
            select(func.count(), func.count(func.distinct(DiseaseMapping.disease_id))).select_from(DiseaseMapping)
        ).one()
        facts = tx.execute(
            select(DiseaseFeatureEvidence.evidence_type, func.count())
            .group_by(DiseaseFeatureEvidence.evidence_type)
            .order_by(DiseaseFeatureEvidence.evidence_type)
        ).all()
        pairs = tx.execute(
            select(DiseaseFeatureEvidence.disease_id, DiseaseFeatureEvidence.feature_id, func.count())
            .group_by(DiseaseFeatureEvidence.disease_id, DiseaseFeatureEvidence.feature_id)
            .having(func.count() > 1)
        ).all()
        suggested = tx.execute(
            select(RelationSuggestion.subject_type, RelationSuggestion.status, func.count())
            .where(RelationSuggestion.relation == SYNONYM)
            .group_by(RelationSuggestion.subject_type, RelationSuggestion.status)
            .order_by(RelationSuggestion.subject_type, RelationSuggestion.status)
        ).all()
        return {
            "condition_names_from_data_files": {"rows": mappings[0], "conditions": mappings[1]},
            "facts_by_kind": {kind: count for kind, count in facts},
            "condition_and_item_in_more_than_one_fact": {
                "pairs": len(pairs),
                "rows": sum(count for _disease, _feature, count in pairs),
            },
            "conditions_same_spelling": _same_spelling(
                tx, Disease, Disease.disease_id, Disease.redirected_to.is_(None)
            ),
            "items_same_spelling": _same_spelling(tx, Feature, Feature.feature_id, Feature.feature_id.is_not(None)),
            "pairs_suggested_as_the_same": [
                {"kind": kind, "status": status, "pairs": count} for kind, status, count in suggested
            ],
            "texts_stored_twice_for_one_condition": len(duplicate_texts(tx)),
        }


def condition_groups(tx: Any, exceptions: list[dict[str, Any]]) -> dict[str, Any]:
    """The condition names that are one condition by rule, grouped, with the name to keep for each group.

    Returns the groups to merge, and what was left for a person with the reason."""
    left_out = {frozenset(plain(name) for name in entry["names"]): entry["reason"] for entry in exceptions}
    suggestions = tx.scalars(
        select(RelationSuggestion)
        .where(
            RelationSuggestion.subject_type == "disease",
            RelationSuggestion.relation == SYNONYM,
            RelationSuggestion.status == "pending",
        )
        .order_by(RelationSuggestion.suggestion_id)
    ).all()
    labels = {row.disease_id: row for row in tx.scalars(select(Disease)).all()}
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    skipped, used = [], []
    for suggestion in suggestions:
        left, right = labels.get(suggestion.left_id), labels.get(suggestion.right_id)
        if left is None or right is None or left.redirected_to or right.redirected_to:
            continue  # one of the two is merged already
        reason = left_out.get(frozenset((plain(left.preferred_name), plain(right.preferred_name))))
        if reason:
            skipped.append({"names": [left.preferred_name, right.preferred_name], "reason": reason})
            continue
        parent[find(left.disease_id)] = find(right.disease_id)
        used.append(suggestion)
    members: dict[str, list[str]] = {}
    for node in parent:
        members.setdefault(find(node), []).append(node)
    files = dict(tx.execute(select(DiseaseMapping.disease_id, func.count()).group_by(DiseaseMapping.disease_id)).all())
    groups = []
    for ids in sorted(members.values(), key=lambda group: sorted(labels[i].preferred_name for i in group)):
        mine = [s for s in used if s.left_id in ids]
        by_list: dict[str, set[str]] = {}
        for suggestion in mine:
            for signal in suggestion.signals or []:
                if signal.get("signal") == SAME_CODE:
                    by_list.setdefault(signal["vocabulary"], set()).add(signal["code"])
        names = sorted(labels[i].preferred_name for i in ids)
        # Two lists that each match the names to one entry agree with each other. One list that matches them to
        # two of its entries does not: such a group is left for a person.
        if any(len(codes) > 1 for codes in by_list.values()):
            skipped.append(
                {"names": names, "reason": "one reference list matches these names to more than one of its entries"}
            )
            continue
        # The standard name, if a list gives one: MONDO's first, then any other list's.
        title, where = None, None
        for vocabulary in sorted(by_list, key=lambda name: (name != "MONDO", name)):
            title = tx.scalar(
                select(TerminologyLink.title)
                .where(
                    TerminologyLink.system == vocabulary,
                    TerminologyLink.code == next(iter(by_list[vocabulary])),
                    TerminologyLink.disease_id.in_(ids),
                )
                .order_by(TerminologyLink.link_id)
                .limit(1)
            )
            if title:
                where = vocabulary
                break
        # The name to keep is one of our own: the one that is the standard name; otherwise the spelling without an
        # underscore that the most data files use. It takes the standard spelling only when the words are the same,
        # so no name is put on a condition that none of the data files gave it.
        kept = min(
            ids,
            key=lambda i: (
                plain(labels[i].preferred_name) != plain(title or ""),
                "_" in labels[i].preferred_name,
                -files.get(i, 0),
                labels[i].preferred_name,
            ),
        )
        own = labels[kept].preferred_name.replace("_", " ")
        # Our names are written in lower case; a standard name that differs only by capital letters changes nothing.
        adopt = title is not None and plain(title) == plain(own) and title.lower() != own.lower()
        kept_name = title.lower() if adopt and title else own
        groups.append(
            {
                "kept_id": kept,
                "kept_name": kept_name,
                "merged": sorted((i for i in ids if i != kept), key=lambda i: labels[i].preferred_name),
                "names": names,
                "standard_entry": {"vocabulary": where, "title": title} if title else None,
                "suggestions": [suggestion.suggestion_id for suggestion in mine],
            }
        )
    return {"groups": groups, "left_for_a_person": skipped}


def merge_groups(db: Database, principal: Principal, groups: list[dict[str, Any]], note: str) -> dict[str, Any]:
    """Merge every group with the service's own merge, and record the suggestions it rested on as approved."""
    merged, refused, suggestions = 0, [], []
    for group in groups:
        for source_id in group["merged"]:
            try:
                disease_merges.merge(
                    db,
                    principal,
                    source_id=source_id,
                    target_id=group["kept_id"],
                    note=note,
                    kept_name=group["kept_name"],
                )
                merged += 1
            except ApiError as error:
                refused.append(
                    {"label": source_id, "into": group["kept_id"], "code": error.code, "message": error.message}
                )
        suggestions.extend(group["suggestions"])
    decided = (
        review_bulk.decide_each(
            db, principal, target_type="relation_suggestion", target_ids=suggestions, note=note, status="approved"
        )
        if suggestions
        else {"decided": 0, "refused": []}
    )
    return {
        "groups": len(groups),
        "names_merged": merged,
        "merges_refused": refused,
        "suggestions_approved": decided["decided"],
        "suggestions_refused": decided["refused"],
    }


def duplicate_texts(tx: Any) -> list[dict[str, Any]]:
    """Texts stored more than once, word for word, for one condition (a merged name counts as the name kept)."""
    kept_as = {row.disease_id: row.redirected_to or row.disease_id for row in tx.scalars(select(Disease)).all()}
    seen: dict[tuple[str, str, str], list[str]] = {}
    rows = tx.execute(
        select(Statement.statement_id, Statement.disease_id, Statement.statement_type, Statement.text_content)
        .where(Statement.status.in_(("pending", "approved")), Statement.disease_id.is_not(None))
        .order_by(Statement.statement_id)
    ).all()
    for statement_id, disease_id, kind, text in rows:
        key = (kept_as.get(disease_id, disease_id), kind, hashlib.sha256(text.encode()).hexdigest())
        seen.setdefault(key, []).append(statement_id)
    return [
        {"condition": key[0], "kept": ids[0], "copies": ids[1:]} for key, ids in sorted(seen.items()) if len(ids) > 1
    ]


def retire_duplicate_texts(
    db: Database, principal: Principal, note: str, *, conditions: frozenset[str] | None = None
) -> dict[str, Any]:
    """Keep the first of each set of identical texts of one condition and retire the copies, each with its note.

    conditions: only the texts of these conditions (the IDs of the names kept); all conditions when not given."""
    with db.transaction(None, role="migration") as tx:
        found = [entry for entry in duplicate_texts(tx) if conditions is None or entry["condition"] in conditions]
    retired, refused = 0, []
    for entry in found:
        done = review_bulk.decide_each(
            db,
            principal,
            target_type="statement",
            target_ids=entry["copies"],
            note=f"{note} A word-for-word copy of the text {entry['kept']} of the same condition.",
            status="retired",
        )
        retired += done["decided"]
        refused.extend(done["refused"])
    return {"sets": len(found), "copies_retired": retired, "refused": refused}


def main() -> int:
    parser = argparse.ArgumentParser(prog="feeltriva_api.duplicates")
    parser.add_argument("--merge", action="store_true", help="merge the condition names that are one condition by rule")
    parser.add_argument("--reviewer", help="the name the merges are recorded under (with --merge)")
    parser.add_argument("--note", help="the note recorded with every merge (with --merge)")
    args = parser.parse_args()
    settings = get_settings()
    owner = Database(settings.migration_database_url or settings.database_url)
    print(json.dumps(report(owner), indent=2)[:6000])
    with owner.transaction(None, role="migration") as tx:
        found = condition_groups(tx, load_exceptions())
    print(f"condition names that are one condition by rule: {len(found['groups'])} groups")
    for group in found["groups"]:
        print(f'  keep "{group["kept_name"]}" for: {" | ".join(group["names"])}')
    for entry in found["left_for_a_person"]:
        print(f"  left for a person: {' | '.join(entry['names'])}: {entry['reason']}")
    if not args.merge:
        print("nothing was changed (run with --merge, --reviewer and --note to merge)")
        return 0
    if not args.reviewer or not args.note:
        print("--merge needs --reviewer and --note")
        return 2
    principal = Principal(subject=f"dev-reviewer:{args.reviewer}", roles=frozenset({"reviewer"}))
    db = Database(settings.database_url)
    print(json.dumps(merge_groups(db, principal, found["groups"], args.note), indent=2))
    print(json.dumps(retire_duplicate_texts(db, principal, args.note), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
