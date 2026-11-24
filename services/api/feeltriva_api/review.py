"""Internal review workspace and reviewed-only knowledge serving.

Imported mappings and statements are lexical/positional candidates in 'pending' status.
A reviewer decision here changes the record's status and leaves an attributed note; it does
not publish anything. Patient-facing reads return only what is in the current published releases
and is still approved (the serving views, M2.9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import (
    AuditEvent,
    Disease,
    DiseaseMapping,
    Feature,
    FeatureMapping,
    MappingRelease,
    RelationSuggestion,
    ReviewNote,
    Source,
    Statement,
    StatementSource,
    TerminologyLink,
)

REVIEW_STATES = ("pending", "approved", "rejected", "retired")
_TARGETS: dict[str, tuple[Any, str]] = {
    "disease_mapping": (DiseaseMapping, "mapping_id"),
    "feature_mapping": (FeatureMapping, "mapping_id"),
    "statement": (Statement, "statement_id"),
}


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 200)), max(0, offset)


class ReviewService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def overview(self, principal: Principal) -> dict[str, Any]:
        principal.require_role("reviewer")
        with self._db.transaction(principal.subject, role="reviewer") as tx:

            def by_status(model: Any) -> dict[str, int]:
                rows = tx.execute(select(model.status, func.count()).group_by(model.status)).all()
                return {status: count for status, count in rows}

            mappings = list(tx.execute(select(FeatureMapping.transformation)).scalars())
            return {
                "label": "Imported dataset audit - lexical candidates, not clinically approved",
                "sources": tx.execute(select(func.count()).select_from(Source)).scalar_one(),
                "disease_candidates": tx.execute(select(func.count()).select_from(Disease)).scalar_one(),
                "disease_mappings": by_status(DiseaseMapping),
                "feature_mappings": by_status(FeatureMapping),
                "statements": by_status(Statement),
                "relation_suggestions": by_status(RelationSuggestion),
                "terminology_links": by_status(TerminologyLink),
                "feature_columns_with_repeated_header": sum(1 for t in mappings if (t or {}).get("repeated_header")),
                "mapping_releases": [
                    {"release_id": r.release_id, "version": r.version, "status": r.status}
                    for r in tx.execute(select(MappingRelease).order_by(MappingRelease.version)).scalars()
                ],
            }

    def list_disease_mappings(
        self,
        principal: Principal,
        *,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        principal.require_role("reviewer")
        limit, offset = _page(limit, offset)
        stmt = select(DiseaseMapping, Disease.preferred_name).join(
            Disease, Disease.disease_id == DiseaseMapping.disease_id, isouter=True
        )
        if status:
            stmt = stmt.where(DiseaseMapping.status == status)
        if q:
            stmt = stmt.where(func.lower(DiseaseMapping.original_label).contains(q.lower()))
        with self._db.transaction(principal.subject, role="reviewer") as tx:
            total = tx.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = tx.execute(
                stmt.order_by(DiseaseMapping.original_label, DiseaseMapping.mapping_id).limit(limit).offset(offset)
            ).all()
            return {
                "total": total,
                "items": [
                    {
                        "mapping_id": m.mapping_id,
                        "source_id": m.source_id,
                        "original_term": m.original_label,
                        "original_id": m.original_id,
                        "proposed_canonical_id": m.disease_id,
                        "proposed_canonical_term": name,
                        "mapping_method": m.method,
                        "review_status": m.status,
                        "reviewer": m.reviewer,
                    }
                    for m, name in rows
                ],
            }

    def list_feature_mappings(
        self,
        principal: Principal,
        *,
        status: str | None = None,
        q: str | None = None,
        conflicts_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        principal.require_role("reviewer")
        limit, offset = _page(limit, offset)
        stmt = select(FeatureMapping)
        if status:
            stmt = stmt.where(FeatureMapping.status == status)
        if q:
            stmt = stmt.where(func.lower(FeatureMapping.original_term).contains(q.lower()))
        with self._db.transaction(principal.subject, role="reviewer") as tx:
            rows = list(
                tx.execute(
                    stmt.order_by(FeatureMapping.source_id, FeatureMapping.file_path, FeatureMapping.column_index)
                ).scalars()
            )
            if conflicts_only:
                rows = [m for m in rows if (m.transformation or {}).get("repeated_header")]
            return {
                "total": len(rows),
                "items": [
                    {
                        "mapping_id": m.mapping_id,
                        "source_id": m.source_id,
                        "file_path": m.file_path,
                        "column_index": m.column_index,
                        "original_term": m.original_term,
                        "proposed_canonical_id": m.feature_id,
                        "zero_semantics": m.zero_semantics,
                        "review_status": m.status,
                        "conflicts": m.transformation or {},
                    }
                    for m in rows[offset : offset + limit]
                ],
            }

    def list_statements(
        self,
        principal: Principal,
        *,
        status: str | None = None,
        statement_type: str | None = None,
        disease_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        principal.require_role("reviewer")
        limit, offset = _page(limit, offset)
        stmt = select(Statement)
        if status:
            stmt = stmt.where(Statement.status == status)
        if statement_type:
            stmt = stmt.where(Statement.statement_type == statement_type)
        if disease_id:
            stmt = stmt.where(Statement.disease_id == disease_id)
        with self._db.transaction(principal.subject, role="reviewer") as tx:
            total = tx.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = list(tx.execute(stmt.order_by(Statement.statement_id).limit(limit).offset(offset)).scalars())
            sources: dict[str, list[dict[str, Any]]] = {}
            if rows:
                for s in tx.execute(
                    select(StatementSource).where(StatementSource.statement_id.in_([r.statement_id for r in rows]))
                ).scalars():
                    sources.setdefault(s.statement_id, []).append(
                        {"record_id": s.record_id, "source_url": s.source_url, "text_span": s.text_span}
                    )
            return {
                "total": total,
                "items": [
                    {
                        "statement_id": r.statement_id,
                        "disease_id": r.disease_id,
                        "statement_type": r.statement_type,
                        "original_statement": r.text_content,
                        "applicability": r.applicability,
                        "review_status": r.status,
                        "reviewed_by": r.reviewed_by,
                        "sources": sources.get(r.statement_id, []),
                    }
                    for r in rows
                ],
            }

    def list_relation_suggestions(
        self,
        principal: Principal,
        *,
        status: str | None = None,
        relation: str | None = None,
        subject_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Suggested synonyms and subtypes, each with both terms and the reasons. Nothing is merged
        by a suggestion; accepting or rejecting one is a recorded review decision."""
        principal.require_role("reviewer")
        limit, offset = _page(limit, offset)
        stmt = select(RelationSuggestion)
        if status:
            stmt = stmt.where(RelationSuggestion.status == status)
        if relation:
            stmt = stmt.where(RelationSuggestion.relation == relation)
        if subject_type:
            stmt = stmt.where(RelationSuggestion.subject_type == subject_type)
        if q:
            pattern = q.lower()
            stmt = stmt.where(
                func.lower(RelationSuggestion.left_label).contains(pattern)
                | func.lower(RelationSuggestion.right_label).contains(pattern)
            )
        with self._db.transaction(principal.subject, role="reviewer") as tx:
            total = tx.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = tx.execute(
                stmt.order_by(
                    RelationSuggestion.subject_type, RelationSuggestion.left_label, RelationSuggestion.suggestion_id
                )
                .limit(limit)
                .offset(offset)
            ).scalars()
            return {
                "label": "Suggestions from wording only - not clinically reviewed; nothing is merged until a reviewer decides",
                "total": total,
                "items": [
                    {
                        "suggestion_id": r.suggestion_id,
                        "subject_type": r.subject_type,
                        "relation": r.relation,
                        "left": {"id": r.left_id, "term": r.left_label},
                        "right": {"id": r.right_id, "term": r.right_label},
                        "signals": r.signals or [],
                        "review_status": r.status,
                        "reviewer": r.reviewer,
                    }
                    for r in rows
                ],
            }

    def record_review(
        self, principal: Principal, *, target_type: str, target_id: str, note: str, status: str | None = None
    ) -> dict[str, Any]:
        principal.require_role("reviewer")
        if target_type not in _TARGETS:
            raise ApiError(422, "unknown_review_target", "Unknown review target type.")
        if status is not None and status not in REVIEW_STATES:
            raise ApiError(422, "invalid_review_status", "Unknown review status.")
        if not note.strip() or len(note) > 4000:
            raise ApiError(422, "invalid_note", "A reviewer note of 1 to 4000 characters is required.")
        model, key = _TARGETS[target_type]
        with self._db.transaction(principal.subject, role="reviewer") as tx:
            target = tx.get(model, target_id)
            if target is None:
                raise ApiError(404, "review_target_not_found", "Review target not found.")
            previous = target.status
            if status is not None:
                guard = _GUARDS.get(target_type)
                if guard is not None:  # what a decision on this kind of target requires or entails
                    guard(tx, target, status, principal)
                target.status = status
                if isinstance(target, Statement):
                    target.reviewed_by, target.reviewed_at = principal.subject, datetime.now(UTC)
                elif isinstance(target, DiseaseMapping | RelationSuggestion | TerminologyLink):
                    target.reviewer = principal.subject
            entry = ReviewNote(
                note_id=uuid.uuid4(),
                target_type=target_type,
                target_id=target_id,
                reviewer=principal.subject,
                note=note.strip(),
                status_change=status,
            )
            tx.add(entry)
            tx.add(
                AuditEvent(
                    event_id=uuid.uuid4(),
                    actor_subject=principal.subject,
                    event_type="review_recorded",
                    redacted_metadata={
                        "target_type": target_type,
                        "target_id": target_id,
                        "from": previous,
                        "to": status or previous,
                    },
                )
            )
            return {
                "target_type": target_type,
                "target_id": target_id,
                "previous_status": previous,
                "review_status": target.status,
                "note_id": str(entry.note_id),
                "reviewer": principal.subject,
            }


class KnowledgeService:
    """Reviewed-only reads, from the serving views and from nothing else (M2.9).

    The views hold what is in the current published releases and is still approved, with an approved source and
    not expired (migration 0017). Content that is approved but not published is not served. The views exist in
    PostgreSQL only: on the in-memory SQLite database of the unit tests nothing is available, which is the safe
    answer."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get_condition_information(self, principal: Principal, disease_id: str) -> dict[str, Any]:
        principal.require_scope("knowledge:read")
        unavailable = ApiError(
            404, "condition_not_available", "No reviewed information is available for this condition."
        )
        if not self._db.is_postgres:
            raise unavailable
        with self._db.transaction(principal.subject) as tx:
            # A label merged into another answers with the label it was merged into.
            condition = tx.execute(
                text(
                    "SELECT disease_id, name, definition FROM reviewed_disease_catalog "
                    "WHERE disease_id = :id OR merged_labels @> jsonb_build_array(CAST(:id AS text)) "
                    "ORDER BY (disease_id = :id) DESC LIMIT 1"
                ),
                {"id": disease_id},
            ).first()
            if condition is None:
                raise unavailable
            statements = tx.execute(
                text(
                    "SELECT statement_id, statement_type, text, sources FROM reviewed_condition_statements "
                    "WHERE disease_id = :id ORDER BY statement_type, statement_id"
                ),
                {"id": condition.disease_id},
            ).all()
            return {
                "disease_id": condition.disease_id,
                "name": condition.name,
                "definition": condition.definition,
                "statements": [
                    {
                        "statement_id": row.statement_id,
                        "statement_type": row.statement_type,
                        "text": row.text,
                        # every displayed claim has a source: the view holds no statement without one
                        "sources": [
                            {"record_id": source["record_id"], "source_url": source["source_url"]}
                            for source in row.sources
                        ],
                    }
                    for row in statements
                ],
            }


# Registered here, at the end of the module, so that the decision endpoint also serves suggestions.
_TARGETS["relation_suggestion"] = (RelationSuggestion, "suggestion_id")


def list_terminology_links(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    system: str | None = None,
    subject_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Candidate links to outside vocabularies, each with our own term, for reviewers only (M2.17).

    A link is a match of names or an equivalence stated by a vocabulary; approving or rejecting one is
    a recorded review decision. Codes are internal: this is never part of a user-facing response."""
    principal.require_role("reviewer")
    limit, offset = _page(limit, offset)
    term = func.coalesce(Disease.preferred_name, Feature.preferred_name)
    stmt = (
        select(TerminologyLink, term)
        .outerjoin(Disease, Disease.disease_id == TerminologyLink.disease_id)
        .outerjoin(Feature, Feature.feature_id == TerminologyLink.feature_id)
    )
    if status:
        stmt = stmt.where(TerminologyLink.status == status)
    if system:
        stmt = stmt.where(TerminologyLink.system == system)
    if subject_type == "disease":
        stmt = stmt.where(TerminologyLink.disease_id.is_not(None))
    elif subject_type == "feature":
        stmt = stmt.where(TerminologyLink.feature_id.is_not(None))
    if q:
        pattern = q.lower()
        stmt = stmt.where(
            func.lower(term).contains(pattern)
            | func.lower(TerminologyLink.title).contains(pattern)
            | func.lower(TerminologyLink.code).contains(pattern)
        )
    with db.transaction(principal.subject, role="reviewer") as tx:
        total = tx.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = tx.execute(
            stmt.order_by(term, TerminologyLink.system, TerminologyLink.code, TerminologyLink.link_id)
            .limit(limit)
            .offset(offset)
        ).all()
        return {
            "label": "Candidate links to outside vocabularies - internal, not shown to users; a link is a candidate until a reviewer decides",
            "total": total,
            "items": [
                {
                    "link_id": link.link_id,
                    "subject": {
                        "type": "disease" if link.disease_id else "feature",
                        "id": link.disease_id or link.feature_id,
                        "term": name,
                    },
                    "system": link.system,
                    "system_version": link.system_version,
                    "code": link.code,
                    "title": link.title,
                    "uri": link.uri,
                    "match_method": link.match_method,
                    "detail": link.detail or {},
                    "review_status": link.status,
                    "reviewer": link.reviewer,
                }
                for link, name in rows
            ],
        }


_TARGETS["terminology_link"] = (TerminologyLink, "link_id")


# What a decision on a kind of target requires or entails beyond setting its status (M2.5a). A guard is called
# inside the reviewer's transaction before the status is set; it raises ApiError to refuse the decision.
_GUARDS: dict[str, Any] = {}


# ---- What a decision on a vocabulary link entails (M2.5d2) -------------------------------------------------
#
# 1. A SNOMED CT or ICD-11 link taken through a MONDO link rests on it (`detail.via.link_id`). Rejecting the
#    MONDO link retires the pending links taken through it; withdrawing the rejection makes those pending
#    again. A link taken through it that a reviewer approved is not overruled: the rejection is refused until
#    that link is decided. A link is not approved while the MONDO link it rests on is rejected.
# 2. The general term is the default (owner's rule E64). Where a term has two ICD-11 candidates and one lies
#    under the other, the narrower one is not approved while the broader one is pending or approved; a reviewer
#    who finds that the source names the narrower form rejects the general term first. The same holds for a
#    category and its "unspecified" sub-code (E66): approval keeps the category, and the sub-code row stays as
#    it is, for its provenance.
#
# Which code lies under which is taken from the category WHO names as the parent of an unspecified sub-code,
# where the import recorded it (`detail.category_through_mondo`), and otherwise from the code itself: a code
# that continues another code lies under it. Titles and our own link IDs are named in messages, never a code.
_MONDO, _ICD_MMS = "MONDO", "ICD-11 MMS"
_RETIRED_WITH = "Retired with the MONDO link it was taken through, which a reviewer rejected: "
_PENDING_AGAIN = "Pending again, because the rejection of the MONDO link it was taken through was withdrawn: "


def _taken_through(link: TerminologyLink) -> str | None:
    return ((link.detail or {}).get("via") or {}).get("link_id")


def _lies_under(link: TerminologyLink, other: TerminologyLink) -> bool:
    category = ((link.detail or {}).get("category_through_mondo") or {}).get("icd_code")
    return other.code == category or (len(link.code) > len(other.code) and link.code.startswith(other.code))


def _follow(tx: Any, principal: Principal, link: TerminologyLink, status: str, note: str) -> None:
    """Record a change of one link that follows from a reviewer's decision on another."""
    previous = link.status
    link.status, link.reviewer = status, principal.subject
    tx.add(
        ReviewNote(
            note_id=uuid.uuid4(),
            target_type="terminology_link",
            target_id=link.link_id,
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
                "target_type": "terminology_link",
                "target_id": link.link_id,
                "from": previous,
                "to": status,
                "follows_a_decision_on_another_link": True,
            },
        )
    )


def _link_guard(tx: Any, link: TerminologyLink, status: str, principal: Principal) -> None:
    same_term = (
        TerminologyLink.disease_id == link.disease_id
        if link.disease_id
        else TerminologyLink.feature_id == link.feature_id
    )
    others = tx.scalars(
        select(TerminologyLink)
        .where(same_term, TerminologyLink.link_id != link.link_id)
        .order_by(TerminologyLink.link_id)
    ).all()
    if link.system == _MONDO and status != link.status:
        taken = [other for other in others if _taken_through(other) == link.link_id]
        if status == "rejected":
            approved = [other for other in taken if other.status == "approved"]
            if approved:
                raise ApiError(
                    409,
                    "derived_links_approved",
                    f"{len(approved)} links taken through this MONDO link are approved ("
                    + ", ".join(other.link_id for other in approved)
                    + "). Decide them first: a link cannot stay approved when the link it rests on is rejected.",
                )
            for other in taken:
                if other.status == "pending":
                    _follow(tx, principal, other, "retired", _RETIRED_WITH + link.link_id)
        elif link.status == "rejected":
            for other in taken:
                last = tx.scalars(
                    select(ReviewNote)
                    .where(
                        ReviewNote.target_type == "terminology_link",
                        ReviewNote.target_id == other.link_id,
                        ReviewNote.status_change == "retired",
                    )
                    .order_by(ReviewNote.created_at.desc())
                ).first()
                # Only a link the rejection itself retired comes back; one a reviewer retired stays retired.
                if other.status == "retired" and last is not None and last.note == _RETIRED_WITH + link.link_id:
                    _follow(tx, principal, other, "pending", _PENDING_AGAIN + link.link_id)
    if status != "approved":
        return
    basis_id = _taken_through(link)
    basis = tx.get(TerminologyLink, basis_id) if basis_id else None
    if basis is not None and basis.status == "rejected":
        raise ApiError(
            409,
            "basis_rejected",
            f'This link was taken through the MONDO link "{basis.title}" ({basis.link_id}), which a reviewer '
            "rejected. Withdraw that rejection first if this link is right.",
        )
    if link.system != _ICD_MMS:
        return
    general = [
        other
        for other in others
        if other.system == _ICD_MMS and other.status in ("pending", "approved") and _lies_under(link, other)
    ]
    if general:
        raise ApiError(
            409,
            "general_term_is_default",
            f'This term also has the more general candidate "{general[0].title}" ({general[0].link_id}), and the '
            "general term is the default. Approve that one; or, if the source names the narrower form, reject the "
            "general candidate first.",
        )


_GUARDS["terminology_link"] = _link_guard
