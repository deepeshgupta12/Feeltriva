"""Merging and splitting disease labels, with their history (M2.5c1).

Two labels that name the same disease are merged: one is kept, the other points at it
(`redirected_to`) and stays in the database, so its name remains a synonym of the kept label and
every source row that carries it keeps its own label. Owner's rules (E62): the name kept is the
most accurate standard name, and every merged label is saved as a synonym of it. The reviewer
chooses which label is kept and may give the kept label its standard name; its former name then
stays a synonym too.

A split takes a merged label out again. Every merge and split is one row of a history that is
never changed or deleted, with the reviewer's name and reason. Nothing here decides whether two
labels are the same disease: that is the reviewer's judgement, and a merge can be undone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import AuditEvent, Disease, DiseaseHistory

MERGE, SPLIT = "merge", "split"


def _note(note: str) -> None:
    if not note.strip() or len(note) > 4000:
        raise ApiError(422, "invalid_note", "A note of 1 to 4000 characters is required.")


def _disease(tx: Any, disease_id: str) -> Disease:
    disease = tx.get(Disease, disease_id)
    if disease is None:
        raise ApiError(404, "disease_not_found", "Disease not found.")
    return disease


def _event(tx: Any, principal: Principal, action: str, disease_id: str, other_id: str, detail: dict, note: str) -> None:
    tx.add(
        DiseaseHistory(
            event_id=uuid.uuid4(),
            action=action,
            disease_id=disease_id,
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
            event_type=f"disease_{action}",
            redacted_metadata={"disease_id": disease_id, "other_id": other_id},
        )
    )


def merge(
    db: Database, principal: Principal, *, source_id: str, target_id: str, note: str, kept_name: str | None = None
) -> dict[str, Any]:
    """Merge the label `source_id` into the kept label `target_id`."""
    principal.require_role("reviewer")
    _note(note)
    if source_id == target_id:
        raise ApiError(422, "same_disease", "A label cannot be merged into itself.")
    if kept_name is not None and not (1 <= len(kept_name.strip()) <= 300):
        raise ApiError(422, "invalid_name", "The kept name must have 1 to 300 characters.")
    with db.transaction(principal.subject, role="reviewer") as tx:
        source, target = _disease(tx, source_id), _disease(tx, target_id)
        if source.redirected_to:
            raise ApiError(409, "already_merged", f"This label is already merged into {source.redirected_to}.")
        if target.redirected_to:
            raise ApiError(
                409,
                "target_is_merged",
                f"The label to keep is itself merged into {target.redirected_to}. Merge into that one.",
            )
        # Labels merged into the source earlier follow it: nothing may point at a label that is no longer kept.
        followers = tx.scalars(select(Disease).where(Disease.redirected_to == source_id)).all()
        detail = {
            "merged_name": source.preferred_name,
            "kept_name": target.preferred_name,
            "renamed_to": None,
            "status_before": source.status,
            "moved_with_it": sorted(follower.disease_id for follower in followers),
        }
        for follower in followers:
            follower.redirected_to = target_id
        source.redirected_to, source.status = target_id, "retired"
        if kept_name is not None and kept_name.strip() != target.preferred_name:
            detail["renamed_to"] = kept_name.strip()
            target.preferred_name = kept_name.strip()
        _event(tx, principal, MERGE, source_id, target_id, detail, note)
        tx.flush()
        return _state(tx, target_id)


def split(db: Database, principal: Principal, *, disease_id: str, note: str) -> dict[str, Any]:
    """Take a merged label out of the label it was merged into. It gets back the status it had."""
    principal.require_role("reviewer")
    _note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        disease = _disease(tx, disease_id)
        if not disease.redirected_to:
            raise ApiError(409, "not_merged", "This label is not merged into another.")
        kept_id = disease.redirected_to
        merged = tx.scalars(
            select(DiseaseHistory)
            .where(DiseaseHistory.action == MERGE, DiseaseHistory.disease_id == disease_id)
            .order_by(DiseaseHistory.created_at.desc())
        ).first()
        status = (merged.detail or {}).get("status_before", "pending") if merged is not None else "pending"
        disease.redirected_to, disease.status = None, status
        _event(
            tx,
            principal,
            SPLIT,
            disease_id,
            kept_id,
            {"split_name": disease.preferred_name, "status_after": status},
            note,
        )
        tx.flush()
        return _state(tx, kept_id)


def _state(tx: Any, disease_id: str) -> dict[str, Any]:
    """The kept label a disease resolves to, its synonyms, and the merges and splits that touched either."""
    asked = _disease(tx, disease_id)
    kept = asked
    for _hop in range(10):  # a chain is flattened at every merge; this only guards against a damaged one
        if not kept.redirected_to:
            break
        kept = _disease(tx, kept.redirected_to)
    merged = tx.scalars(
        select(Disease).where(Disease.redirected_to == kept.disease_id).order_by(Disease.disease_id)
    ).all()
    ids = {asked.disease_id, kept.disease_id}
    events = tx.scalars(
        select(DiseaseHistory)
        .where(or_(DiseaseHistory.disease_id.in_(ids), DiseaseHistory.other_id.in_(ids)))
        .order_by(DiseaseHistory.created_at, DiseaseHistory.event_id)
    ).all()
    former = [
        event.detail["kept_name"]
        for event in events
        if event.action == MERGE and event.other_id == kept.disease_id and (event.detail or {}).get("renamed_to")
    ]
    synonyms = list(dict.fromkeys([*(label.preferred_name for label in merged), *former]))
    return {
        "disease_id": asked.disease_id,
        "kept": {"disease_id": kept.disease_id, "preferred_name": kept.preferred_name, "review_status": kept.status},
        "synonyms": [name for name in synonyms if name != kept.preferred_name],
        "merged_labels": [{"disease_id": label.disease_id, "preferred_name": label.preferred_name} for label in merged],
        "history": [
            {
                "action": event.action,
                "disease_id": event.disease_id,
                "other_id": event.other_id,
                "detail": event.detail or {},
                "reviewer": event.reviewer,
                "note": event.note,
                "at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
    }


def state(db: Database, principal: Principal, disease_id: str) -> dict[str, Any]:
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        return _state(tx, disease_id)
