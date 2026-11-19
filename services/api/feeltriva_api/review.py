"""Internal review workspace and reviewed-only knowledge serving.

Imported mappings and statements are lexical/positional candidates in 'pending' status.
A reviewer decision here changes the record's status and leaves an attributed note; it does
not publish anything. Patient-facing reads only ever return 'approved' content.
"""

from __future__ import annotations

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
    """Reviewed-only reads. Pending, rejected, retired or expired content is never returned."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get_condition_information(self, principal: Principal, disease_id: str) -> dict[str, Any]:
        principal.require_scope("knowledge:read")
        with self._db.transaction(principal.subject) as tx:
            disease = tx.get(Disease, disease_id)
            if disease is not None and disease.redirected_to:
                disease = tx.get(Disease, disease.redirected_to)
            if disease is None or disease.status != "approved":
                raise ApiError(
                    404, "condition_not_available", "No reviewed information is available for this condition."
                )
            now = datetime.now(UTC)
            statements = [
                s
                for s in tx.execute(
                    select(Statement)
                    .where(Statement.disease_id == disease.disease_id, Statement.status == "approved")
                    .order_by(Statement.statement_type, Statement.statement_id)
                ).scalars()
                if s.expires_at is None
                or (s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=UTC)) > now
            ]
            out = []
            for s in statements:
                sources = list(
                    tx.execute(select(StatementSource).where(StatementSource.statement_id == s.statement_id)).scalars()
                )
                if not sources:
                    continue  # every displayed claim needs a source
                out.append(
                    {
                        "statement_id": s.statement_id,
                        "statement_type": s.statement_type,
                        "text": s.text_content,
                        "sources": [{"record_id": x.record_id, "source_url": x.source_url} for x in sources],
                    }
                )
            return {
                "disease_id": disease.disease_id,
                "name": disease.preferred_name,
                "definition": disease.definition,
                "statements": out,
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
