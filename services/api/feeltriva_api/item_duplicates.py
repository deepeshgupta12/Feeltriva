"""Which names of symptoms and other items are one item by rule, and merging them (M2.20).

Three grounds, none of them a medical judgement (decision E105):

- the same words with other punctuation ("cross eyed", "cross-eyed");
- a pair suggested as the same because the words are the same in another order, number or spelling
  ("pain in eye", "eye pain"; "diarrhoea", "diarrhea"), unless a reviewer rejected the pair;
- a repeated column heading of a data file ("regurgitation.1" beside "regurgitation"): the same name written
  twice.

A pair that shares only a code of a reference list is never a ground: one code can cover different things
("bladder mass", "kidney mass"). A group is left for a person when its names do not hold the same kind of value,
or when more than one of them is named by a rule or a question.

The name kept is the one a rule or question names; otherwise not a repeated heading, then the name the most data
files use, then the shortest, then the first in the alphabet. Merging uses the service's own merge
(`feature_merges`): nothing is deleted and every merge can be taken out again.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select

from . import feature_merges, review_bulk
from .auth import Principal
from .db import Database
from .duplicates import SYNONYM, plain
from .errors import ApiError
from .models import Feature, FeatureMapping, RelationSuggestion

SAME_WORDS = frozenset(
    {"same_words_other_punctuation", "same_words_other_order_or_number", "british_or_american_spelling"}
)
_NUMBERED = re.compile(r"^(.*\S)\s*[. ]\s*\d+$")


def item_groups(tx: Any) -> dict[str, Any]:
    """The item names that are one item by rule, grouped, with the name to keep for each group.

    Returns the groups to merge, and what was left for a person with the reason."""
    items = {row.feature_id: row for row in tx.scalars(select(Feature).where(Feature.redirected_to.is_(None))).all()}
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join(left: str, right: str) -> None:
        parent[find(left)] = find(right)

    by_words: dict[str, list[str]] = {}
    for feature_id, item in sorted(items.items()):
        by_words.setdefault(plain(item.preferred_name), []).append(feature_id)
    for same in by_words.values():
        for other in same[1:]:
            join(same[0], other)
    headings: set[str] = set()
    for feature_id, item in items.items():
        numbered = _NUMBERED.match(item.preferred_name)
        base = by_words.get(plain(numbered.group(1))) if numbered else None
        if base and feature_id not in base:
            headings.add(feature_id)
            join(feature_id, base[0])
    suggestions = tx.scalars(
        select(RelationSuggestion)
        .where(
            RelationSuggestion.subject_type == "feature",
            RelationSuggestion.relation == SYNONYM,
            RelationSuggestion.status.in_(("pending", "approved")),
        )
        .order_by(RelationSuggestion.suggestion_id)
    ).all()
    used = []
    for suggestion in suggestions:
        signals = {entry.get("signal") for entry in suggestion.signals or []}
        if suggestion.left_id in items and suggestion.right_id in items and signals & SAME_WORDS:
            join(suggestion.left_id, suggestion.right_id)
            used.append(suggestion)
    members: dict[str, list[str]] = {}
    for node in parent:
        members.setdefault(find(node), []).append(node)
    files = dict(tx.execute(select(FeatureMapping.feature_id, func.count()).group_by(FeatureMapping.feature_id)).all())
    in_use = feature_merges.named_in_use(tx)
    groups, skipped = [], []
    for ids in sorted(members.values(), key=lambda group: sorted(items[i].preferred_name for i in group)):
        if len(ids) < 2:
            continue
        names = sorted(items[i].preferred_name for i in ids)
        if len({(items[i].value_type, items[i].unit) for i in ids}) > 1:
            skipped.append({"names": names, "reason": "these names do not hold the same kind of value"})
            continue
        ruled = [i for i in ids if i in in_use]
        if len(ruled) > 1:
            skipped.append({"names": names, "reason": "more than one of these names is named by a rule or a question"})
            continue
        kept = min(
            ids,
            key=lambda i: (
                i not in ruled,
                i in headings,
                -files.get(i, 0),
                len(plain(items[i].preferred_name)),
                items[i].preferred_name,
            ),
        )
        mine = [s for s in used if s.left_id in ids]
        groups.append(
            {
                "kept_id": kept,
                "kept_name": items[kept].preferred_name,
                "merged": sorted((i for i in ids if i != kept), key=lambda i: items[i].preferred_name),
                "names": names,
                "repeated_heading": any(i in headings for i in ids),
                "suggestions": [s.suggestion_id for s in mine if s.status == "pending"],
            }
        )
    return {"groups": groups, "left_for_a_person": skipped}


def merge_item_groups(db: Database, principal: Principal, groups: list[dict[str, Any]], note: str) -> dict[str, Any]:
    """Merge every group with the service's own merge, and record the pending suggestions it rested on as approved."""
    merged, refused, suggestions = 0, [], []
    for group in groups:
        for source_id in group["merged"]:
            try:
                feature_merges.merge(db, principal, source_id=source_id, target_id=group["kept_id"], note=note)
                merged += 1
            except ApiError as error:
                refused.append(
                    {"item": source_id, "into": group["kept_id"], "code": error.code, "message": error.message}
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
