"""Merging and splitting the names of symptoms and other items, with their history (M2.20).

Two names for one item are merged as two condition names are (`disease_merges`, M2.5c1): one is kept,
the other points at it (`redirected_to`), is set to `retired` and stays in the database. Its name
remains another name of the kept item, and every column, fact and sentence that carries it keeps what
it was given; a published list of names and a knowledge version read it through the kept item.

Two things are refused that have no counterpart for conditions:

- an item that an urgency rule or a follow-up question names is not merged away, because the rule
  would then name an item that is no longer in use: the other name is merged into it instead;
- two items that do not hold the same kind of value (yes or no, a number, a unit) are not merged.

A split takes a merged name out again. Every merge and split is one row of a history that is never
changed or deleted. Nothing here decides whether two names are one item: that is the reviewer's
judgement, and a merge can be undone.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import AuditEvent, ClinicalRule, Feature, FeatureHistory, FollowupQuestion

MERGE, SPLIT = "merge", "split"
_IN_USE = ("pending", "approved")  # a rule or question in one of these states still counts
_QUOTED = re.compile(r'"([^"\\]+)"')  # every quoted text of a stored rule: an item's ID is one of them


def _note(note: str) -> None:
    if not note.strip() or len(note) > 4000:
        raise ApiError(422, "invalid_note", "A note of 1 to 4000 characters is required.")


def _feature(tx: Any, feature_id: str) -> Feature:
    feature = tx.get(Feature, feature_id)
    if feature is None:
        raise ApiError(404, "feature_not_found", "Item not found.")
    return feature


def named_in_use(tx: Any) -> dict[str, list[str]]:
    """For every item that a rule or question in use names: the IDs of those rules and questions. Read once for
    many items; a rule is searched as stored, whatever shape its condition has."""
    found: dict[str, list[str]] = {}
    rules = tx.execute(
        select(ClinicalRule.rule_id, ClinicalRule.condition_ast)
        .where(ClinicalRule.status.in_(_IN_USE))
        .order_by(ClinicalRule.rule_id)
    ).all()
    for rule_id, condition in rules:
        for name in dict.fromkeys(_QUOTED.findall(json.dumps(condition))):
            found.setdefault(name, []).append(rule_id)
    questions = tx.execute(
        select(FollowupQuestion.question_id, FollowupQuestion.feature_id)
        .where(FollowupQuestion.feature_id.is_not(None), FollowupQuestion.status.in_(_IN_USE))
        .order_by(FollowupQuestion.question_id)
    ).all()
    for question_id, feature_id in questions:
        found.setdefault(feature_id, []).append(question_id)
    return found


def named_by(tx: Any, feature_id: str) -> list[str]:
    """The rules and questions in use that name this item, by their own IDs."""
    return named_in_use(tx).get(feature_id, [])


def _event(tx: Any, principal: Principal, action: str, feature_id: str, other_id: str, detail: dict, note: str) -> None:
    tx.add(
        FeatureHistory(
            event_id=uuid.uuid4(),
            action=action,
            feature_id=feature_id,
            other_id=other_id,
            detail=detail,
            reviewer=principal.subject,
            note=note.strip(),
            created_at=datetime.now(UTC),  # set here, to the microsecond: the order of events is the history
        )
    )
    tx.add(
        AuditEvent(
            event_id=uuid.uuid4(),
            actor_subject=principal.subject,
            event_type=f"feature_{action}",
            redacted_metadata={"feature_id": feature_id, "other_id": other_id},
        )
    )


def merge(db: Database, principal: Principal, *, source_id: str, target_id: str, note: str) -> dict[str, Any]:
    """Merge the item name `source_id` into the kept item `target_id`."""
    principal.require_role("reviewer")
    _note(note)
    if source_id == target_id:
        raise ApiError(422, "same_feature", "An item cannot be merged into itself.")
    with db.transaction(principal.subject, role="reviewer") as tx:
        source, target = _feature(tx, source_id), _feature(tx, target_id)
        if source.redirected_to:
            raise ApiError(409, "already_merged", f"This name is already merged into {source.redirected_to}.")
        if target.redirected_to:
            raise ApiError(
                409,
                "target_is_merged",
                f"The item to keep is itself merged into {target.redirected_to}. Merge into that one.",
            )
        if (source.value_type, source.unit) != (target.value_type, target.unit):
            raise ApiError(
                409,
                "not_the_same_kind_of_value",
                f'"{source.preferred_name}" holds {source.value_type}'
                + (f" in {source.unit}" if source.unit else "")
                + f' and "{target.preferred_name}" holds {target.value_type}'
                + (f" in {target.unit}" if target.unit else "")
                + ". Two items that do not hold the same kind of value are not merged.",
            )
        users = named_by(tx, source_id)
        if users:
            raise ApiError(
                409,
                "item_named_by_a_rule",
                f'"{source.preferred_name}" is named by {len(users)} rules or questions in use ('
                + ", ".join(users[:5])
                + f'). Keep this one and merge "{target.preferred_name}" into it instead.',
            )
        # Names merged into the source earlier follow it: nothing may point at a name that is no longer kept.
        followers = tx.scalars(select(Feature).where(Feature.redirected_to == source_id)).all()
        detail = {
            "merged_name": source.preferred_name,
            "kept_name": target.preferred_name,
            "status_before": source.status,
            "moved_with_it": sorted(follower.feature_id for follower in followers),
        }
        for follower in followers:
            follower.redirected_to = target_id
        source.redirected_to, source.status = target_id, "retired"
        _event(tx, principal, MERGE, source_id, target_id, detail, note)
        tx.flush()
        return _state(tx, target_id)


def split(db: Database, principal: Principal, *, feature_id: str, note: str) -> dict[str, Any]:
    """Take a merged name out of the item it was merged into. It gets back the status it had."""
    principal.require_role("reviewer")
    _note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        feature = _feature(tx, feature_id)
        if not feature.redirected_to:
            raise ApiError(409, "not_merged", "This name is not merged into another.")
        kept_id = feature.redirected_to
        merged = tx.scalars(
            select(FeatureHistory)
            .where(FeatureHistory.action == MERGE, FeatureHistory.feature_id == feature_id)
            .order_by(FeatureHistory.created_at.desc())
        ).first()
        status = (merged.detail or {}).get("status_before", "pending") if merged is not None else "pending"
        feature.redirected_to, feature.status = None, status
        _event(
            tx,
            principal,
            SPLIT,
            feature_id,
            kept_id,
            {"split_name": feature.preferred_name, "status_after": status},
            note,
        )
        tx.flush()
        return _state(tx, kept_id)


def other_names(kept: Feature, merged: list[Feature]) -> list[str]:
    """The other names of a kept item: its own, then the names merged into it and theirs. Used by the review
    screens and by a published list of names, so both say the same."""
    names = [*(kept.aliases or []), *(name for item in merged for name in (item.preferred_name, *(item.aliases or [])))]
    return [name for name in dict.fromkeys(names) if name != kept.preferred_name]


def _state(tx: Any, feature_id: str) -> dict[str, Any]:
    """The kept item a name resolves to, its other names, and the merges and splits that touched either."""
    asked = _feature(tx, feature_id)
    kept = asked
    for _hop in range(10):  # a chain is flattened at every merge; this only guards against a damaged one
        if not kept.redirected_to:
            break
        kept = _feature(tx, kept.redirected_to)
    merged = list(
        tx.scalars(select(Feature).where(Feature.redirected_to == kept.feature_id).order_by(Feature.feature_id)).all()
    )
    ids = {asked.feature_id, kept.feature_id}
    events = tx.scalars(
        select(FeatureHistory)
        .where(or_(FeatureHistory.feature_id.in_(ids), FeatureHistory.other_id.in_(ids)))
        .order_by(FeatureHistory.created_at, FeatureHistory.event_id)
    ).all()
    return {
        "feature_id": asked.feature_id,
        "kept": {"feature_id": kept.feature_id, "preferred_name": kept.preferred_name, "review_status": kept.status},
        "other_names": other_names(kept, merged),
        "merged_items": [{"feature_id": item.feature_id, "preferred_name": item.preferred_name} for item in merged],
        "named_by": named_by(tx, kept.feature_id),
        "history": [
            {
                "action": event.action,
                "feature_id": event.feature_id,
                "other_id": event.other_id,
                "detail": event.detail or {},
                "reviewer": event.reviewer,
                "note": event.note,
                "at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
    }


def state(db: Database, principal: Principal, feature_id: str) -> dict[str, Any]:
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        return _state(tx, feature_id)
