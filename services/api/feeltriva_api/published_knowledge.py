"""Evidence and sources in the review path, and the published knowledge release (M2.5c3).

A reviewer decides an evidence row and a source through the same decision endpoint as every
other review target. Deciding a source is deciding its provenance: that its licence and origin
allow its content to be used. Nothing here decides that for the reviewer.

A knowledge release is a snapshot of the approved statements and evidence at the time it is
published, pinned to the mapping release that is current at that moment. It holds

- the approved statements that have not expired, each with the source records it rests on;
- the approved evidence rows (a disease, a feature and what links them);
- the sources that content comes from, with their licence and SHA-256.

Unapproved content cannot be published, and approved content is held back, and counted, when

- its source is not approved (a statement keeps only the attributions whose source is approved);
- its disease or feature is not in the pinned mapping release (a merged label counts as the
  label it was merged into);
- a statement has no source, or has expired;
- an evidence row rests on a statement that is not in this release.

A release is refused when no mapping release is current, when the current one belongs to another
mapping working set than this knowledge set names, or when nothing would be in it. Publishing
serves nothing: the serving views read the current release in a later sub-step.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from . import publishing
from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import (
    Disease,
    DiseaseFeatureEvidence,
    Feature,
    KnowledgeRelease,
    PublishedKnowledge,
    PublishedMapping,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from .published_mappings import _decisions
from .review import _TARGETS, REVIEW_STATES, _page

KIND = "knowledge_release"
COUNTED = ("statements", "evidence", "sources")
HELD = (
    "statements_expired",
    "statements_without_source",
    "statements_source_not_approved",
    "statements_disease_not_in_mapping_release",
    "evidence_disease_or_feature_not_in_mapping_release",
    "evidence_statement_not_in_release",
    "evidence_source_not_approved",
)

_TARGETS["evidence"] = (DiseaseFeatureEvidence, "evidence_id")
_TARGETS["source"] = (Source, "source_id")


def list_sources(db: Database, principal: Principal) -> dict[str, Any]:
    """The sources with what is recorded about their origin and licence, for reviewers only."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        sources = tx.scalars(select(Source).order_by(Source.source_name, Source.source_id)).all()
        last = _decisions(tx, "source", [source.source_id for source in sources])
        return {
            "label": "A source is approved when a reviewer has decided that its licence and origin allow its "
            "content to be used. Only content of approved sources enters a knowledge release.",
            "items": [
                {
                    "source_id": source.source_id,
                    "name": source.source_name,
                    "version": source.version,
                    "origin_url": source.origin_url,
                    "licence": source.licence,
                    "permitted_uses": source.permitted_uses or {},
                    "review_status": source.provenance_status,
                    "decided_by": last[source.source_id].reviewer if source.source_id in last else None,
                    "decision_note": last[source.source_id].note if source.source_id in last else None,
                }
                for source in sources
            ],
        }


def list_evidence(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    evidence_type: str | None = None,
    disease_id: str | None = None,
    feature_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """The proposed links between diseases and features, each with what it rests on, for reviewers only."""
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    limit, offset = _page(limit, offset)
    row = DiseaseFeatureEvidence
    filters = [
        column == value
        for column, value in (
            (row.status, status),
            (row.evidence_type, evidence_type),
            (row.disease_id, disease_id),
            (row.feature_id, feature_id),
        )
        if value
    ]
    with db.transaction(principal.subject, role="reviewer") as tx:
        total = tx.scalar(select(func.count()).select_from(row).where(*filters)) or 0
        rows = tx.execute(
            select(row, Disease.preferred_name, Feature.preferred_name)
            .join(Disease, Disease.disease_id == row.disease_id)
            .join(Feature, Feature.feature_id == row.feature_id)
            .where(*filters)
            .order_by(row.evidence_id)
            .limit(limit)
            .offset(offset)
        ).all()
        return {
            "label": "Proposed links between a disease and a feature - a count in a sample or a mention in a text "
            "is not a clinical claim; nothing is used until a reviewer approves it",
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "evidence_id": item.evidence_id,
                    "disease": {"id": item.disease_id, "term": disease},
                    "feature": {"id": item.feature_id, "term": feature},
                    "relationship": item.relationship,
                    "evidence_type": item.evidence_type,
                    "context": item.context or {},
                    "frequency": float(item.frequency) if item.frequency is not None else None,
                    "frequency_denominator": item.frequency_denominator,
                    "statement_id": item.statement_id,
                    "record_id": item.record_id,
                    "review_status": item.status,
                }
                for item, disease, feature in rows
            ],
        }


def _expired(statement: Statement, now: datetime) -> bool:
    if statement.expires_at is None:
        return False
    end = statement.expires_at if statement.expires_at.tzinfo else statement.expires_at.replace(tzinfo=UTC)
    return end <= now


def _content(tx: Any, working: KnowledgeRelease, now: datetime) -> tuple[dict[str, Any], list[str]]:
    """What a release of this knowledge set would hold now, and everything that keeps it from being published."""
    problems: list[str] = []
    pinned = publishing.current(tx, PublishedMapping)
    diseases: set[str] = set()
    features: set[str] = set()
    redirects: dict[str, str] = {}
    if pinned is None:
        problems.append("no mapping release is current")
    else:
        if working.mapping_release_id and pinned.working_id != working.mapping_release_id:
            problems.append(
                f"the current mapping release {pinned.release_id} is not of the mapping working set "
                f"{working.mapping_release_id} this knowledge set names"
            )
        diseases = {entry["disease_id"] for entry in pinned.content["diseases"]}
        features = {entry["feature_id"] for entry in pinned.content["features"]}
        redirects = dict(pinned.content["redirects"])
    sources = {source.source_id: source for source in tx.scalars(select(Source)).all()}
    cleared = {source_id for source_id, source in sources.items() if source.provenance_status == "approved"}
    held = dict.fromkeys(HELD, 0)

    def kept(disease_id: str) -> str | None:
        target = redirects.get(disease_id, disease_id)
        return target if target in diseases else None

    attributions: dict[str, list[dict[str, Any]]] = {}
    for link, source_id in tx.execute(
        select(StatementSource, SourceRecord.source_id)
        .join(SourceRecord, SourceRecord.record_id == StatementSource.record_id)
        .join(Statement, Statement.statement_id == StatementSource.statement_id)
        .where(Statement.status == "approved")
        .order_by(StatementSource.statement_id, StatementSource.record_id)
    ).all():
        attributions.setdefault(link.statement_id, []).append(
            {
                "record_id": link.record_id,
                "source_id": source_id,
                "source_url": link.source_url,
                "text_span": link.text_span,
            }
        )
    approved = 0
    statements: list[dict[str, Any]] = []
    for statement in tx.scalars(
        select(Statement).where(Statement.status == "approved").order_by(Statement.statement_id)
    ).all():
        approved += 1
        basis = [entry for entry in attributions.get(statement.statement_id, []) if entry["source_id"] in cleared]
        target = kept(statement.disease_id) if statement.disease_id else None
        if _expired(statement, now):
            held["statements_expired"] += 1
        elif statement.statement_id not in attributions:
            held["statements_without_source"] += 1
        elif not basis:
            held["statements_source_not_approved"] += 1
        elif statement.disease_id and target is None:
            held["statements_disease_not_in_mapping_release"] += 1
        else:
            statements.append(
                {
                    "statement_id": statement.statement_id,
                    "disease_id": statement.disease_id,
                    "resolves_to": target,
                    "statement_type": statement.statement_type,
                    "text": statement.text_content,
                    "applicability": statement.applicability or {},
                    "reviewed_by": statement.reviewed_by,
                    "reviewed_at": statement.reviewed_at.isoformat() if statement.reviewed_at else None,
                    "expires_at": statement.expires_at.isoformat() if statement.expires_at else None,
                    "sources": basis,
                }
            )
    in_release = {statement["statement_id"] for statement in statements}
    origin = dict(
        tx.execute(
            select(DiseaseFeatureEvidence.evidence_id, SourceRecord.source_id)
            .join(SourceRecord, SourceRecord.record_id == DiseaseFeatureEvidence.record_id)
            .where(DiseaseFeatureEvidence.status == "approved")
        ).all()
    )
    evidence: list[dict[str, Any]] = []
    for row in tx.scalars(
        select(DiseaseFeatureEvidence)
        .where(DiseaseFeatureEvidence.status == "approved")
        .order_by(DiseaseFeatureEvidence.evidence_id)
    ).all():
        approved += 1
        target = kept(row.disease_id)
        source_id = origin.get(row.evidence_id)
        if target is None or row.feature_id not in features:
            held["evidence_disease_or_feature_not_in_mapping_release"] += 1
        elif row.statement_id is not None and row.statement_id not in in_release:
            held["evidence_statement_not_in_release"] += 1
        elif row.record_id is not None and source_id not in cleared:
            held["evidence_source_not_approved"] += 1
        else:
            evidence.append(
                {
                    "evidence_id": row.evidence_id,
                    "disease_id": row.disease_id,
                    "resolves_to": target,
                    "feature_id": row.feature_id,
                    "relationship": row.relationship,
                    "evidence_type": row.evidence_type,
                    "context": row.context or {},
                    "frequency": float(row.frequency) if row.frequency is not None else None,
                    "frequency_denominator": row.frequency_denominator,
                    "statement_id": row.statement_id,
                    "record_id": row.record_id,
                    "source_id": source_id,
                }
            )
    used = sorted(
        {entry["source_id"] for statement in statements for entry in statement["sources"]}
        | {row["source_id"] for row in evidence if row["source_id"]}
    )
    if not statements and not evidence:
        problems.append(
            "every approved statement and evidence row is held back"
            if approved
            else "no statement and no evidence is approved"
        )

    def pending(model: Any, column: Any) -> int:
        return tx.scalar(select(func.count()).select_from(model).where(column == "pending")) or 0

    content = {
        "knowledge_release_id": working.release_id,
        "version": working.version,
        "mapping_release": {"release_id": pinned.release_id, "sha256": pinned.sha256} if pinned is not None else None,
        "statements": statements,
        "evidence": evidence,
        "sources": [
            {
                "source_id": source_id,
                "source_name": sources[source_id].source_name,
                "version": sources[source_id].version,
                "origin_url": sources[source_id].origin_url,
                "licence": sources[source_id].licence,
                "permitted_uses": sources[source_id].permitted_uses or {},
                "sha256": sources[source_id].sha256,
            }
            for source_id in used
        ],
        "unresolved": {
            "statements": pending(Statement, Statement.status),
            "evidence": pending(DiseaseFeatureEvidence, DiseaseFeatureEvidence.status),
            "sources": pending(Source, Source.provenance_status),
        },
        "held_back": held,
    }
    return content, problems


def _counts(content: dict[str, Any]) -> dict[str, Any]:
    return {
        **{part: len(content[part]) for part in COUNTED},
        "unresolved": content["unresolved"],
        "held_back": content["held_back"],
    }


def _summary(tx: Any, release: PublishedKnowledge) -> dict[str, Any]:
    pinned = tx.get(PublishedMapping, release.mapping_release)
    return {
        **publishing.summary(release),
        "knowledge_release_id": release.working_id,
        "mapping_release": release.mapping_release,
        # A knowledge release is read with the mapping release it was published against. After a rollback of
        # either, the two current releases may no longer belong together; this says whether they do.
        "mapping_release_is_current": bool(pinned is not None and pinned.is_current),
        **_counts(release.content),
    }


def _working(tx: Any, knowledge_release_id: str) -> KnowledgeRelease:
    working = tx.get(KnowledgeRelease, knowledge_release_id)
    if working is None:
        raise ApiError(404, "knowledge_release_not_found", "Knowledge set not found.")
    return working


def list_published(db: Database, principal: Principal) -> dict[str, Any]:
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        releases = tx.scalars(
            select(PublishedKnowledge).order_by(PublishedKnowledge.working_id, PublishedKnowledge.number)
        ).all()
        return {"items": [_summary(tx, release) for release in releases]}


def preview(db: Database, principal: Principal, knowledge_release_id: str) -> dict[str, Any]:
    """What publishing this knowledge set now would do. Changes nothing."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        content, problems = _content(tx, _working(tx, knowledge_release_id), datetime.now(UTC))
        return {
            "knowledge_release_id": knowledge_release_id,
            "mapping_release": (content["mapping_release"] or {}).get("release_id"),
            **publishing.outlook(tx, PublishedKnowledge, knowledge_release_id, content, problems),
            **_counts(content),
        }


def publish(db: Database, principal: Principal, *, knowledge_release_id: str, note: str) -> dict[str, Any]:
    principal.require_role("reviewer")
    publishing.check_note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        content, problems = _content(tx, _working(tx, knowledge_release_id), datetime.now(UTC))
        release = publishing.publish(
            tx,
            PublishedKnowledge,
            principal,
            kind=KIND,
            working_id=knowledge_release_id,
            content=content,
            problems=problems,
            note=note,
            mapping_release=(content["mapping_release"] or {}).get("release_id"),
        )
        return _summary(tx, release)


def make_current(db: Database, principal: Principal, *, release_id: str, note: str) -> dict[str, Any]:
    """Make a published knowledge release the current one (rollback). Nothing is removed."""
    principal.require_role("reviewer")
    publishing.check_note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        release = publishing.make_current(
            tx, PublishedKnowledge, principal, kind=KIND, release_id=release_id, note=note
        )
        return _summary(tx, release)
