"""SQLAlchemy mapping of the tables the application reads/writes.

PostgreSQL is the source of truth and is created by Alembic (migrations/), which also adds
row-level security. Types here are portable so the service logic can be unit-tested on SQLite;
import-only tables (dataset cases, model releases, ...) are handled by the ingestion pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
BigInt = BigInteger().with_variant(Integer(), "sqlite")
ReviewState = SAEnum("pending", "approved", "rejected", "retired", name="review_state", create_type=False)
Presence = SAEnum("present", "absent", "uncertain", "not_asked", name="presence_state", create_type=False)
FeatureKind = SAEnum(
    "symptom",
    "sign",
    "history",
    "risk_factor",
    "measurement",
    "other",
    name="feature_kind",
    create_type=False,
)
TZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


# ---- reference / review zone -------------------------------------------------
class Source(Base):
    __tablename__ = "sources"
    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    origin_url: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(Text)
    permitted_uses: Mapped[Any] = mapped_column(Json, default=dict)
    population: Mapped[Any] = mapped_column(Json, default=dict)
    provenance_status: Mapped[str] = mapped_column(ReviewState, default="pending")
    sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    __table_args__ = (UniqueConstraint("source_name", "version"),)


class SourceRecord(Base):
    __tablename__ = "source_records"
    record_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    file_path: Mapped[str] = mapped_column(Text)
    row_number: Mapped[int | None] = mapped_column(BigInt)
    content_hash: Mapped[str] = mapped_column(Text, index=True)
    raw_object_uri: Mapped[str] = mapped_column(Text)
    original_split: Mapped[str | None] = mapped_column(Text)
    quality_flags: Mapped[Any] = mapped_column(Json, default=list)
    __table_args__ = (UniqueConstraint("source_id", "file_path", "row_number"),)


class MappingRelease(Base):
    __tablename__ = "mapping_releases"
    release_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(TZ)


class Disease(Base):
    __tablename__ = "diseases"
    disease_id: Mapped[str] = mapped_column(Text, primary_key=True)
    preferred_name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    redirected_to: Mapped[str | None] = mapped_column(ForeignKey("diseases.disease_id"))
    external_ids: Mapped[Any] = mapped_column(Json, default=dict)


class DiseaseMapping(Base):
    __tablename__ = "disease_mappings"
    mapping_id: Mapped[str] = mapped_column(Text, primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("mapping_releases.release_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    original_label: Mapped[str] = mapped_column(Text)
    original_id: Mapped[str | None] = mapped_column(Text)
    disease_id: Mapped[str | None] = mapped_column(ForeignKey("diseases.disease_id"))
    method: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    reviewer: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("release_id", "source_id", "original_label"),)


class Feature(Base):
    __tablename__ = "features"
    feature_id: Mapped[str] = mapped_column(Text, primary_key=True)
    preferred_name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(FeatureKind)
    value_type: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[Any] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")


class FeatureMapping(Base):
    __tablename__ = "feature_mappings"
    mapping_id: Mapped[str] = mapped_column(Text, primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("mapping_releases.release_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    file_path: Mapped[str] = mapped_column(Text)
    column_index: Mapped[int | None] = mapped_column(Integer)
    original_term: Mapped[str] = mapped_column(Text)
    feature_id: Mapped[str | None] = mapped_column(ForeignKey("features.feature_id"))
    zero_semantics: Mapped[str] = mapped_column(Text, default="unknown")
    transformation: Mapped[Any] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    __table_args__ = (UniqueConstraint("release_id", "source_id", "file_path", "column_index"),)


class Statement(Base):
    __tablename__ = "statements"
    statement_id: Mapped[str] = mapped_column(Text, primary_key=True)
    disease_id: Mapped[str | None] = mapped_column(ForeignKey("diseases.disease_id"))
    statement_type: Mapped[str] = mapped_column(Text)
    text_content: Mapped[str] = mapped_column(Text)
    applicability: Mapped[Any] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(TZ)
    expires_at: Mapped[datetime | None] = mapped_column(TZ)


class StatementSource(Base):
    __tablename__ = "statement_sources"
    statement_id: Mapped[str] = mapped_column(ForeignKey("statements.statement_id"), primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("source_records.record_id"), primary_key=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    text_span: Mapped[Any | None] = mapped_column(Json)


class KnowledgeRelease(Base):
    __tablename__ = "knowledge_releases"
    release_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mapping_release_id: Mapped[str | None] = mapped_column(ForeignKey("mapping_releases.release_id"))
    version: Mapped[str] = mapped_column(Text, unique=True)
    manifest_uri: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")


class RuleBundle(Base):
    __tablename__ = "rule_bundles"
    bundle_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    manifest_uri: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(TZ)


class FollowupQuestion(Base):
    __tablename__ = "followup_questions"
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("rule_bundles.bundle_id"))
    feature_id: Mapped[str | None] = mapped_column(ForeignKey("features.feature_id"))
    wording: Mapped[str] = mapped_column(Text)
    answer_schema: Mapped[Any] = mapped_column(Json)
    applicability: Mapped[Any] = mapped_column(Json)
    branch_rules: Mapped[Any] = mapped_column(Json)
    evidence_ids: Mapped[Any] = mapped_column(Json)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")


class ReviewNote(Base):
    __tablename__ = "review_notes"
    note_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    status_change: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


# ---- private live-session zone (owner-scoped; RLS in PostgreSQL) -------------
class Session(Base):
    __tablename__ = "sessions"
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    owner_subject: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    observation_version: Mapped[int] = mapped_column(BigInt, default=0)
    consent_version: Mapped[str] = mapped_column(Text)
    demographics: Mapped[Any] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TZ)
    deleted_at: Mapped[datetime | None] = mapped_column(TZ)


class SessionMessage(Base):
    __tablename__ = "session_messages"
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class SessionObservation(Base):
    __tablename__ = "session_observations"
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_messages.message_id", ondelete="SET NULL"))
    feature_id: Mapped[str | None] = mapped_column(ForeignKey("features.feature_id"))
    raw_phrase_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    presence: Mapped[str] = mapped_column(Presence)
    value: Mapped[Any | None] = mapped_column(Json)
    modifiers: Mapped[Any] = mapped_column(Json, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    observation_version: Mapped[int] = mapped_column(BigInt)
    supersedes: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_observations.observation_id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class SessionAnswer(Base):
    __tablename__ = "session_answers"
    answer_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(ForeignKey("followup_questions.question_id"))
    value: Mapped[Any] = mapped_column(Json)
    observation_version: Mapped[int] = mapped_column(BigInt)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class Assessment(Base):
    __tablename__ = "assessments"
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    observation_version: Mapped[int] = mapped_column(BigInt)
    status: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(Text)
    candidates: Mapped[Any] = mapped_column(Json, default=list)
    unknowns: Mapped[Any] = mapped_column(Json, default=list)
    evidence_ids: Mapped[Any] = mapped_column(Json, default=list)
    model_release_id: Mapped[str | None] = mapped_column(Text)
    knowledge_release_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_releases.release_id"))
    rule_bundle_id: Mapped[str | None] = mapped_column(ForeignKey("rule_bundles.bundle_id"))
    prompt_version: Mapped[str] = mapped_column(Text)
    provider_model_id: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[Any] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.session_id", ondelete="SET NULL"))
    actor_subject: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    redacted_metadata: Mapped[Any] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    owner_subject: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    response_status: Mapped[int | None] = mapped_column(Integer)
    encrypted_response: Mapped[bytes | None] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(TZ)


class RelationSuggestion(Base):
    """A suggested relation between two candidates, for a reviewer to accept or reject (M2.8)."""

    __tablename__ = "relation_suggestions"
    suggestion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text)
    left_id: Mapped[str] = mapped_column(Text)
    right_id: Mapped[str] = mapped_column(Text)
    left_label: Mapped[str] = mapped_column(Text)
    right_label: Mapped[str] = mapped_column(Text)
    signals: Mapped[Any] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    reviewer: Mapped[str | None] = mapped_column(Text)


class TerminologyLink(Base):
    """A candidate link from one of our disease or feature candidates to a term of an outside vocabulary.

    Written by the ingestion pipeline (M2.11, M2.14 to M2.16). The API only reads these rows and records a
    reviewer's decision on them (M2.17), and only inside a reviewer transaction. Codes are internal: no
    user-facing response carries them (decision E63)."""

    __tablename__ = "terminology_links"
    link_id: Mapped[str] = mapped_column(Text, primary_key=True)
    disease_id: Mapped[str | None] = mapped_column(Text)
    feature_id: Mapped[str | None] = mapped_column(Text)
    system: Mapped[str] = mapped_column(Text)
    system_version: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(Text)
    match_method: Mapped[str] = mapped_column(Text)
    detail: Mapped[Any] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")
    reviewer: Mapped[str | None] = mapped_column(Text)


class ClinicalRule(Base):
    """A rule of a rule bundle (urgency or scope), kept for review (M2.10). Serving never reads this table:
    it reads a published release bundle, and only an approved one in clinical mode."""

    __tablename__ = "clinical_rules"
    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("rule_bundles.bundle_id"))
    rule_type: Mapped[str] = mapped_column(Text)
    applicability: Mapped[Any] = mapped_column(Json)
    condition_ast: Mapped[Any] = mapped_column(Json)
    action: Mapped[Any] = mapped_column(Json)
    evidence_ids: Mapped[Any] = mapped_column(Json)
    priority: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(ReviewState, default="pending")


class RuleRelease(Base):
    """A published snapshot of the approved rules of a bundle (M2.5b). Never edited or deleted: the database
    refuses it. Only `is_current` changes, and at most one release is current."""

    __tablename__ = "rule_releases"
    __table_args__ = (UniqueConstraint("bundle_id", "number"),)
    release_id: Mapped[str] = mapped_column(Text, primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("rule_bundles.bundle_id"))
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[Any] = mapped_column(Json)
    sha256: Mapped[str] = mapped_column(Text)
    rule_file_fingerprint: Mapped[str | None] = mapped_column(Text)
    published_by: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
