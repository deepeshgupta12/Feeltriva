"""Shared machinery of the assessment service: construction, idempotent execution, owner-scoped
session loading, observation versions, current-observation resolution and audit."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from feeltriva_clinical import (
    Facts,
    ReleaseBundle,
    answer_in_words,
    screen,
)
from feeltriva_inference import CandidateProvider
from feeltriva_llm import Extractor, VocabularyTerm
from feeltriva_retrieval import EvidenceProvider
from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as Tx

from . import schemas as sc
from .auth import Principal
from .crypto import FieldCipher
from .db import Database
from .errors import ApiError, not_found, stale_version
from .models import (
    AuditEvent,
    IdempotencyKey,
    Session,
    SessionObservation,
)
from .settings import Settings

log = logging.getLogger(__name__)
REASSESS_STATES = {"result_ready", "insufficient_information", "system_unavailable", "assessing"}
CONTEXT = "clinically_relevant_context"  # the part of a session's demographics that holds context answers
# What is known about a symptom beside its presence: kept with the observation, returned as given (M3.12).
ATTRIBUTES = ("location", "pattern", "triggers", "relieving_factors")
PAUSED_STATES = {"urgent_handoff", "out_of_scope", "closed"}


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ProviderFailure(Exception):
    pass


class ServiceCore:
    def __init__(
        self,
        *,
        db: Database,
        settings: Settings,
        cipher: FieldCipher,
        bundle: ReleaseBundle,
        extractor: Extractor,
        candidates: CandidateProvider,
        evidence: EvidenceProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db, self._settings, self._cipher, self._bundle = db, settings, cipher, bundle
        self._extractor, self._candidates, self._evidence = extractor, candidates, evidence
        self._now = clock or (lambda: datetime.now(UTC))
        self._vocabulary = [VocabularyTerm(f.feature_id, tuple(f.aliases)) for f in bundle.features]

    # ------------------------------------------------------------------ helpers
    def _idempotent(
        self,
        principal: Principal,
        key: str,
        operation: str,
        session_id: uuid.UUID | None,
        payload: Any,
        fn: Callable[[Tx], tuple[dict[str, Any], uuid.UUID]],
    ) -> dict[str, Any]:
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ApiError(400, "invalid_idempotency_key", "Idempotency-Key must be 1 to 128 characters.")
        request_hash = hashlib.sha256(
            json.dumps([operation, str(session_id), payload], sort_keys=True, default=str).encode()
        ).hexdigest()
        with self._db.transaction(principal.subject) as tx:
            now = self._now()
            record = tx.get(IdempotencyKey, (principal.subject, key))
            if record is not None and aware(record.expires_at) <= now:
                tx.delete(record)
                tx.flush()
                record = None
            if record is not None:
                if record.request_hash != request_hash:
                    raise ApiError(
                        409,
                        "idempotency_key_conflict",
                        "This Idempotency-Key was already used for a different request.",
                    )
                if record.state == "completed" and record.encrypted_response is not None:
                    return json.loads(self._cipher.decrypt(record.encrypted_response))
                raise ApiError(409, "request_in_progress", "This request is still being processed.", retryable=True)
            record = IdempotencyKey(
                owner_subject=principal.subject,
                key=key,
                request_hash=request_hash,
                operation=operation,
                state="in_progress",
                expires_at=now + timedelta(minutes=self._settings.idempotency_ttl_minutes),
            )
            tx.add(record)
            try:
                tx.flush()
            except IntegrityError as exc:  # a concurrent request holds the same key
                raise ApiError(
                    409, "request_in_progress", "This request is still being processed.", retryable=True
                ) from exc
            body, owned_session_id = fn(tx)
            record.session_id = owned_session_id
            record.response_status = 200
            record.encrypted_response = self._cipher.encrypt(json.dumps(body))
            record.state = "completed"
            return body

    def _load(
        self,
        tx: Tx,
        principal: Principal,
        session_id: uuid.UUID,
        *,
        lock: bool = False,
        allow_expired: bool = False,
    ) -> Session:
        stmt = select(Session).where(
            Session.session_id == session_id,
            Session.owner_subject == principal.subject,
            Session.deleted_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        session = tx.execute(stmt).scalar_one_or_none()
        if session is None:
            raise not_found()
        if not allow_expired and aware(session.expires_at) <= self._now():
            raise ApiError(403, "session_expired", "This session has ended. Start a new symptom check.")
        return session

    def _bump(self, tx: Tx, session: Session, expected: int) -> int:
        if session.observation_version != expected:
            raise stale_version(session.observation_version)
        result = cast(
            CursorResult[Any],
            tx.execute(
                update(Session)
                .where(Session.session_id == session.session_id, Session.observation_version == expected)
                .values(observation_version=expected + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:  # lost a race with another tab / MCP client
            raise stale_version(expected + 1)
        tx.refresh(session)
        return expected + 1

    def _current(self, tx: Tx, session_id: uuid.UUID) -> list[SessionObservation]:
        rows = list(
            tx.execute(
                select(SessionObservation)
                .where(SessionObservation.session_id == session_id)
                .order_by(SessionObservation.observation_version, SessionObservation.created_at)
            ).scalars()
        )
        superseded = {r.supersedes for r in rows if r.supersedes is not None}
        return [r for r in rows if r.observation_id not in superseded]

    def _facts(self, current: list[SessionObservation], demographics: dict[str, Any], *, confirmed_only: bool) -> Facts:
        presence = {o.feature_id: o.presence for o in current if o.feature_id and (o.confirmed or not confirmed_only)}
        # What the person answered about clinically relevant context (M3.9), for the context questions of the rule
        # set only. It is kept apart from what they report, and the self-described gender is never read: nothing
        # about a person is concluded from it.
        context = (demographics or {}).get(CONTEXT) or {}
        for question in self._bundle.questions:
            entry = context.get(question.feature_id) if question.stores == "context" else None
            if isinstance(entry, dict) and entry.get("presence") in ("present", "absent", "uncertain"):
                presence[question.feature_id] = entry["presence"]
        return Facts(presence, {"demographics.age_years": (demographics or {}).get("age_years")})

    def _record(self, o: SessionObservation) -> sc.ObservationRecord:
        mods = o.modifiers or {}
        item = self._bundle.feature(o.feature_id) if o.feature_id else None
        return sc.ObservationRecord(
            feature_id=o.feature_id,
            presence=cast(sc.PresenceT, o.presence),
            value=o.value,
            onset=mods.get("onset"),
            duration=mods.get("duration"),
            severity=mods.get("severity"),
            **{name: mods.get(name) for name in ATTRIBUTES},
            display_name=item.preferred_name if item else None,
            value_label=self._in_words(o),
            confirmed=o.confirmed,
            supersedes=o.supersedes,
            observation_id=o.observation_id,
            observation_version=o.observation_version,
            raw_phrase=self._cipher.decrypt(o.raw_phrase_encrypted) if o.raw_phrase_encrypted else None,
        )

    def _in_words(self, o: SessionObservation) -> str | None:
        """The stored answer of an observation as a person reads it: the words of the option that was chosen, a
        number with its unit, a date written out. None when there is nothing to say, and never a stored internal
        value (M3.12; the same words the summary uses)."""
        asked: list[dict[str, Any] | None] = [
            q.answer_schema for q in self._bundle.questions if q.feature_id == o.feature_id
        ] or [None]
        return next((said for said in (answer_in_words(schema, o.value) for schema in asked) if said), None)

    def _session_out(self, session: Session, current: list[SessionObservation]) -> dict[str, Any]:
        demographics = sc.Demographics(**session.demographics) if session.demographics else None
        return sc.dump(
            sc.SessionOut(
                session_id=session.session_id,
                observation_version=session.observation_version,
                state=session.state,
                expires_at=aware(session.expires_at),
                observations=[self._record(o) for o in current],
                demographics=demographics,
            )
        )

    def _state_after_change(self, previous: str, facts: Facts) -> str:
        screening = screen(self._bundle, facts)
        if screening.escalation:
            return "urgent_handoff"
        if screening.scope_exclusion:
            return "out_of_scope"
        return "assessing" if previous in REASSESS_STATES else "clarifying"

    def _audit(self, tx: Tx, principal: Principal, session_id: uuid.UUID | None, event: str, **meta: Any) -> None:
        # Metadata is counts/versions/identifiers only. Never symptom text.
        tx.add(
            AuditEvent(
                event_id=uuid.uuid4(),
                session_id=session_id,
                actor_subject=principal.subject,
                event_type=event,
                redacted_metadata=meta,
            )
        )
