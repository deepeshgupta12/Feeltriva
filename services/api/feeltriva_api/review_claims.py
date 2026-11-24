"""Single claims and text chunks in the review path, and what an approval makes (M2.5e).

A reviewer decides a claim and a chunk through the same decision endpoint as every other review
target. Two approvals make something, in the reviewer's own transaction and under the reviewer's
name:

- An approved list item that names a feature becomes one evidence row for that disease and
  feature, resting on the statement. It is made once: approving again makes no second row. When
  the approval is withdrawn, the evidence row is retired; it comes back with a new approval.
- An approved chunk of a text file becomes one statement, with the file's source record and the
  chunk's place in the file. Its type is taken from the source's own section heading. When the
  approval is withdrawn, the statement is retired. A chunk that is a list of references is not a
  statement and is not approved.

Neither puts anything into what is served: an evidence row and a statement reach a person only
through a published knowledge release.

A reviewer can also say for whom or when a claim holds (its applicability), in words. Nothing
interprets those words yet.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import (
    AuditEvent,
    Disease,
    DiseaseFeatureEvidence,
    EvidenceChunk,
    Feature,
    ReviewNote,
    Statement,
    StatementClaim,
    StatementSource,
)
from .review import _GUARDS, _TARGETS, REVIEW_STATES, _page

LIST_ITEM = "list_item"
EVIDENCE_TYPE, RELATIONSHIP = "reviewed_claim", "listed_as_symptom_in_statement"
# What a reviewer should check on a claim that carries one of these marks (decision E74).
MARKS = {
    "cut_off": "The source cut this text off: the sentence is not whole, and the last item of a list in it was dropped.",
    "first_item_preposition": "The first item of this list holds a preposition. The other items may share its first "
    'words ("infection with viruses, bacteria, fungi") or may not ("loss of appetite, nausea, vomiting").',
}
# The statement type of a chunk, from the heading of the section the source put it under. Anything else, and
# the opening part of a text, is a description.
_SECTION_TYPES = {
    "signs and symptoms": "symptom",
    "symptoms": "symptom",
    "causes": "cause",
    "cause": "cause",
    "treatment": "treatment",
    "management": "management",
    "prevention": "prevention",
}

_TARGETS["claim"] = (StatementClaim, "claim_id")
_TARGETS["chunk"] = (EvidenceChunk, "chunk_id")


def _made_id(prefix: str, kind: str, source_id: str) -> str:
    return prefix + hashlib.sha256(f"{kind}\x1f{source_id}".encode()).hexdigest()[:24]


def evidence_id_of(claim_id: str) -> str:
    return _made_id("ev_", "claim", claim_id)


def statement_id_of(chunk_id: str) -> str:
    return _made_id("st_", "chunk", chunk_id)


def statement_type_of(chunk: EvidenceChunk) -> str:
    path = (chunk.details or {}).get("section_path") or []
    return _SECTION_TYPES.get(str(path[0]).strip().lower(), "description") if path else "description"


def _follow(tx: Any, principal: Principal, target_type: str, target_id: str, status: str, note: str) -> None:
    """The decision record of a row that was made or changed by a reviewer's decision on another row."""
    tx.add(
        ReviewNote(
            note_id=uuid.uuid4(),
            target_type=target_type,
            target_id=target_id,
            reviewer=principal.subject,
            note=note,
            status_change=status,
        )
    )
    tx.add(
        AuditEvent(
            event_id=uuid.uuid4(),
            actor_subject=principal.subject,
            event_type="review_recorded",
            redacted_metadata={
                "target_type": target_type,
                "target_id": target_id,
                "to": status,
                "follows_a_decision_on_another_row": True,
            },
        )
    )


def _claim_guard(tx: Any, claim: StatementClaim, status: str, principal: Principal) -> None:
    claim.reviewer = principal.subject
    if claim.kind != LIST_ITEM or claim.proposed_feature_id is None:
        return
    evidence_id = evidence_id_of(claim.claim_id)
    made = tx.get(DiseaseFeatureEvidence, evidence_id)
    if status != "approved":
        if made is not None and made.status == "approved":
            made.status = "retired"
            _follow(
                tx,
                principal,
                "evidence",
                evidence_id,
                "retired",
                f"Retired with the claim it was made from, whose approval was withdrawn: {claim.claim_id}",
            )
        return
    statement = tx.get(Statement, claim.statement_id)
    if statement is None or statement.disease_id is None:
        raise ApiError(409, "claim_has_no_disease", "The statement of this claim names no disease.")
    if made is None:
        tx.add(
            DiseaseFeatureEvidence(
                evidence_id=evidence_id,
                disease_id=statement.disease_id,
                feature_id=claim.proposed_feature_id,
                statement_id=claim.statement_id,
                relationship=RELATIONSHIP,
                context={
                    "claim_id": claim.claim_id,
                    "claim_text": claim.claim_text,
                    "span": [claim.span_start, claim.span_end],
                    "rule": claim.rule,
                    "basis": "an item of the statement's own list whose name is the name of this feature, approved by "
                    "a reviewer",
                },
                evidence_type=EVIDENCE_TYPE,
                status="approved",
            )
        )
        _follow(tx, principal, "evidence", evidence_id, "approved", f"Made from the approved claim {claim.claim_id}")
    elif made.status != "approved":
        made.status = "approved"
        _follow(tx, principal, "evidence", evidence_id, "approved", f"Approved again with its claim {claim.claim_id}")


def _chunk_guard(tx: Any, chunk: EvidenceChunk, status: str, principal: Principal) -> None:
    chunk.reviewer = principal.subject
    details = chunk.details or {}
    statement_id = statement_id_of(chunk.chunk_id)
    made = tx.get(Statement, statement_id)
    now = datetime.now(UTC)
    if status != "approved":
        if made is not None and made.status == "approved":
            made.status, made.reviewed_by, made.reviewed_at = "retired", principal.subject, now
            _follow(
                tx,
                principal,
                "statement",
                statement_id,
                "retired",
                f"Retired with the text chunk it was made from, whose approval was withdrawn: {chunk.chunk_id}",
            )
        return
    if details.get("boilerplate"):
        raise ApiError(
            409,
            "chunk_is_boilerplate",
            "This part of the text is a list of references or links, not a statement about the condition.",
        )
    disease = tx.get(Disease, details.get("disease_id") or "")
    if disease is None or chunk.record_id is None:
        raise ApiError(409, "chunk_has_no_disease", "This chunk names no disease label or no source record.")
    if made is None:
        tx.add(
            Statement(
                statement_id=statement_id,
                disease_id=disease.disease_id,
                statement_type=statement_type_of(chunk),
                text_content=chunk.chunk_text,
                status="approved",
                reviewed_by=principal.subject,
                reviewed_at=now,
            )
        )
        tx.flush()
        tx.add(
            StatementSource(
                statement_id=statement_id,
                record_id=chunk.record_id,
                source_url=details.get("source_url"),
                text_span={
                    "chunk_id": chunk.chunk_id,
                    "file": details.get("file"),
                    "char_start": details.get("char_start"),
                    "char_end": details.get("char_end"),
                    "section_path": details.get("section_path") or [],
                    "extraction_version": details.get("extraction_version"),
                },
            )
        )
        _follow(tx, principal, "statement", statement_id, "approved", f"Made from the approved chunk {chunk.chunk_id}")
    elif made.status != "approved":
        made.status, made.reviewed_by, made.reviewed_at = "approved", principal.subject, now
        _follow(tx, principal, "statement", statement_id, "approved", f"Approved again with its chunk {chunk.chunk_id}")
    chunk.statement_id = statement_id


_GUARDS["claim"] = _claim_guard
_GUARDS["chunk"] = _chunk_guard


def _claim_out(claim: StatementClaim, features: dict[str, str]) -> dict[str, Any]:
    cues = claim.cues or {}
    return {
        "claim_id": claim.claim_id,
        "kind": claim.kind,
        "text": claim.claim_text,
        "span": [claim.span_start, claim.span_end],
        "cues": cues,
        "marks": [mark for mark in MARKS if mark in cues],
        "rule": claim.rule,
        "superseded_by": claim.superseded_by,
        "proposed_feature": (
            {"id": claim.proposed_feature_id, "term": features.get(claim.proposed_feature_id)}
            if claim.proposed_feature_id
            else None
        ),
        "applicability": claim.applicability,
        "review_status": claim.status,
        "reviewer": claim.reviewer,
    }


def list_claims(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    mark: str | None = None,
    statement_type: str | None = None,
    disease_id: str | None = None,
    statement_id: str | None = None,
    with_feature: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Statements with their single claims, each sentence with the items of its lists, for reviewers only.

    The filters choose the statements: a statement is listed when one of its claims fits. Statements with a
    claim that carries a mark (`cut_off`, `first_item_preposition`) come first, so that they are read first."""
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    if mark is not None and mark not in MARKS:
        raise ApiError(422, "unknown_mark", "Unknown mark: " + ", ".join(MARKS) + " are the marks.")
    limit, offset = _page(limit, offset)
    with db.transaction(principal.subject, role="reviewer") as tx:
        fits = select(StatementClaim.statement_id, StatementClaim.cues, StatementClaim.proposed_feature_id).join(
            Statement, Statement.statement_id == StatementClaim.statement_id
        )
        if status:
            fits = fits.where(StatementClaim.status == status)
        if statement_type:
            fits = fits.where(Statement.statement_type == statement_type)
        if disease_id:
            fits = fits.where(Statement.disease_id == disease_id)
        if statement_id:
            fits = fits.where(StatementClaim.statement_id == statement_id)
        marked: dict[str, bool] = {}
        for owner, cues, feature in tx.execute(fits).all():
            carried = [name for name in MARKS if name in (cues or {})]
            if (mark and mark not in carried) or (with_feature and feature is None):
                continue
            marked[owner] = marked.get(owner, False) or bool(carried)
        chosen = sorted(marked, key=lambda owner: (not marked[owner], owner))
        page = chosen[offset : offset + limit]
        statements = {
            row.statement_id: row for row in tx.scalars(select(Statement).where(Statement.statement_id.in_(page))).all()
        }
        claims = (
            tx.scalars(
                select(StatementClaim)
                .where(StatementClaim.statement_id.in_(page))
                .order_by(StatementClaim.statement_id, StatementClaim.span_start, StatementClaim.kind.desc())
            ).all()
            if page
            else []
        )
        wanted = {claim.proposed_feature_id for claim in claims if claim.proposed_feature_id}
        features = dict(
            tx.execute(select(Feature.feature_id, Feature.preferred_name).where(Feature.feature_id.in_(wanted))).all()
        )
        labels = dict(
            tx.execute(
                select(Disease.disease_id, Disease.preferred_name).where(
                    Disease.disease_id.in_({row.disease_id for row in statements.values() if row.disease_id})
                )
            ).all()
        )
        tally = tx.execute(select(StatementClaim.status, func.count()).group_by(StatementClaim.status)).all()
        items = []
        for owner in page:
            statement = statements[owner]
            sentences: dict[str, dict[str, Any]] = {}
            for claim in claims:
                if claim.statement_id != owner:
                    continue
                entry = _claim_out(claim, features)
                if claim.parent_claim_id is None:
                    sentences[claim.claim_id] = {**entry, "items": []}
                elif claim.parent_claim_id in sentences:
                    sentences[claim.parent_claim_id]["items"].append(entry)
            items.append(
                {
                    "statement_id": owner,
                    "statement_type": statement.statement_type,
                    "disease": {"id": statement.disease_id, "term": labels.get(statement.disease_id or "")},
                    "text": statement.text_content,
                    "review_status": statement.status,
                    "has_a_mark": marked[owner],
                    "claims": list(sentences.values()),
                }
            )
        return {
            "label": "Single claims taken from the statements by rules of wording - not clinically reviewed; a claim is "
            "used for nothing until a reviewer approves it",
            "marks": MARKS,
            "claims_by_status": {state: count for state, count in tally},
            "total": len(chosen),
            "limit": limit,
            "offset": offset,
            "items": items,
        }


def set_applicability(
    db: Database, principal: Principal, *, claim_id: str, text: str | None, note: str
) -> dict[str, Any]:
    """Record for whom or when a claim holds, in the reviewer's words. `None` removes what was recorded."""
    principal.require_role("reviewer")
    if not note.strip() or len(note) > 4000:
        raise ApiError(422, "invalid_note", "A note of 1 to 4000 characters is required.")
    if text is not None and not (1 <= len(text.strip()) <= 500):
        raise ApiError(422, "invalid_applicability", "The applicability is 1 to 500 characters of text, or nothing.")
    with db.transaction(principal.subject, role="reviewer") as tx:
        claim = tx.get(StatementClaim, claim_id)
        if claim is None:
            raise ApiError(404, "claim_not_found", "Claim not found.")
        claim.applicability = (
            {"text": text.strip(), "set_by": principal.subject, "set_at": datetime.now(UTC).isoformat()}
            if text is not None
            else None
        )
        tx.add(
            ReviewNote(
                note_id=uuid.uuid4(),
                target_type="claim",
                target_id=claim_id,
                reviewer=principal.subject,
                note=note.strip(),
                status_change=None,
            )
        )
        tx.add(
            AuditEvent(
                event_id=uuid.uuid4(),
                actor_subject=principal.subject,
                event_type="claim_applicability_set",
                redacted_metadata={"claim_id": claim_id, "set": text is not None},
            )
        )
        tx.flush()
        return {"claim_id": claim_id, "applicability": claim.applicability, "review_status": claim.status}


def list_chunks(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    disease_id: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """The parts of the narrative text files, each with its place in its file, for reviewers only."""
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    limit, offset = _page(limit, offset)
    filters = []
    if status:
        filters.append(EvidenceChunk.status == status)
    if disease_id:
        filters.append(EvidenceChunk.details["disease_id"].as_string() == disease_id)
    if q:
        filters.append(func.lower(EvidenceChunk.chunk_text).contains(q.lower()))
    with db.transaction(principal.subject, role="reviewer") as tx:
        tally = tx.execute(select(EvidenceChunk.status, func.count()).group_by(EvidenceChunk.status)).all()
        total = tx.scalar(select(func.count()).select_from(EvidenceChunk).where(*filters)) or 0
        rows = tx.scalars(
            select(EvidenceChunk).where(*filters).order_by(EvidenceChunk.chunk_id).limit(limit).offset(offset)
        ).all()
        items = []
        for chunk in rows:
            details = chunk.details or {}
            items.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "disease": {"id": details.get("disease_id"), "term": details.get("disease_label")},
                    "file": details.get("file"),
                    "section_path": details.get("section_path") or [],
                    "span": [details.get("char_start"), details.get("char_end")],
                    "text": chunk.chunk_text,
                    "source_url": details.get("source_url"),
                    "is_references_or_links": bool(details.get("boilerplate")),
                    "statement_type_if_approved": statement_type_of(chunk),
                    "statement_id": chunk.statement_id,
                    "review_status": chunk.status,
                    "reviewer": chunk.reviewer,
                }
            )
        return {
            "label": "Parts of the narrative text files - not clinically reviewed; approving a part makes it a "
            "statement, which is shown to nobody until a knowledge release holds it",
            "chunks_by_status": {state: count for state, count in tally},
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }
