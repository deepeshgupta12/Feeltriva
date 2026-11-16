"""Application service for assessments. REST and MCP both call this class and nothing else:
ownership, consent, idempotency, observation versions, urgency/scope screening and response
shaping all live here so no transport can bypass them."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from feeltriva_clinical import (
    AnswerValidationError,
    Facts,
    ReleaseBundle,
    interpret_answer,
    next_question,
    screen,
)
from feeltriva_inference import CandidateProvider
from feeltriva_llm import ExtractionError, Extractor, VocabularyTerm
from feeltriva_retrieval import EvidenceProvider
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as Tx

from . import schemas as sc
from .auth import Principal
from .crypto import FieldCipher
from .db import Database
from .errors import ApiError, not_found, stale_version
from .models import (
    Assessment,
    AuditEvent,
    IdempotencyKey,
    Session,
    SessionAnswer,
    SessionMessage,
    SessionObservation,
)
from .settings import Settings

log = logging.getLogger(__name__)
_REASSESS_STATES = {"result_ready", "insufficient_information", "system_unavailable", "assessing"}
_PAUSED_STATES = {"urgent_handoff", "out_of_scope", "closed"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class _ProviderFailure(Exception):
    pass


class AssessmentService:
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
            if record is not None and _aware(record.expires_at) <= now:
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
        if not allow_expired and _aware(session.expires_at) <= self._now():
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

    @staticmethod
    def _facts(current: list[SessionObservation], demographics: dict[str, Any], *, confirmed_only: bool) -> Facts:
        presence = {o.feature_id: o.presence for o in current if o.feature_id and (o.confirmed or not confirmed_only)}
        return Facts(presence, {"demographics.age_years": (demographics or {}).get("age_years")})

    def _record(self, o: SessionObservation) -> sc.ObservationRecord:
        mods = o.modifiers or {}
        return sc.ObservationRecord(
            feature_id=o.feature_id,
            presence=cast(sc.PresenceT, o.presence),
            value=o.value,
            onset=mods.get("onset"),
            duration=mods.get("duration"),
            severity=mods.get("severity"),
            confirmed=o.confirmed,
            supersedes=o.supersedes,
            observation_id=o.observation_id,
            observation_version=o.observation_version,
            raw_phrase=self._cipher.decrypt(o.raw_phrase_encrypted) if o.raw_phrase_encrypted else None,
        )

    def _session_out(self, session: Session, current: list[SessionObservation]) -> dict[str, Any]:
        demographics = sc.Demographics(**session.demographics) if session.demographics else None
        return sc.dump(
            sc.SessionOut(
                session_id=session.session_id,
                observation_version=session.observation_version,
                state=session.state,
                expires_at=_aware(session.expires_at),
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
        return "assessing" if previous in _REASSESS_STATES else "clarifying"

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

    # --------------------------------------------------------------- operations
    def start_session(self, principal: Principal, payload: sc.SessionCreate, idempotency_key: str) -> dict[str, Any]:
        principal.require_scope("assessment:write")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            demographics = payload.demographics.model_dump(exclude_none=True) if payload.demographics else {}
            facts = self._facts([], demographics, confirmed_only=False)
            state = "out_of_scope" if screen(self._bundle, facts).scope_exclusion else "intake"
            session = Session(
                session_id=uuid.uuid4(),
                owner_subject=principal.subject,
                state=state,
                observation_version=0,
                consent_version=payload.consent_version,
                demographics=demographics,
                expires_at=self._now() + timedelta(minutes=self._settings.session_ttl_minutes),
            )
            tx.add(session)
            tx.flush()
            self._audit(
                tx,
                principal,
                session.session_id,
                "session_started",
                consent_version=payload.consent_version,
                state=state,
            )
            return self._session_out(session, []), session.session_id

        return self._idempotent(principal, idempotency_key, "start_session", None, payload.model_dump(mode="json"), fn)

    def get_session(self, principal: Principal, session_id: uuid.UUID) -> dict[str, Any]:
        principal.require_scope("assessment:read")
        with self._db.transaction(principal.subject) as tx:
            session = self._load(tx, principal, session_id)
            return self._session_out(session, self._current(tx, session_id))

    def submit_observations(
        self, principal: Principal, session_id: uuid.UUID, payload: sc.ObservationSubmit, idempotency_key: str
    ) -> dict[str, Any]:
        principal.require_scope("assessment:write")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            session = self._load(tx, principal, session_id, lock=True)
            if session.observation_version != payload.observation_version:
                raise stale_version(session.observation_version)
            current = self._current(tx, session_id)
            by_id = {o.observation_id: o for o in current}
            by_feature = {o.feature_id: o for o in current if o.feature_id}
            new_rows: list[SessionObservation] = []
            if payload.text is not None:
                try:
                    extraction = self._extractor.extract(payload.text, self._vocabulary)
                except ExtractionError as exc:
                    # Nothing is stored; the client keeps the text and may retry. A failed
                    # extraction is never treated as "no symptoms".
                    raise ApiError(
                        503,
                        "extraction_unavailable",
                        "We couldn't process your message. Nothing was saved; please try again.",
                        retryable=True,
                    ) from exc
                version = self._bump(tx, session, payload.observation_version)
                message = SessionMessage(
                    message_id=uuid.uuid4(),
                    session_id=session_id,
                    role="user",
                    encrypted_content=self._cipher.encrypt(payload.text),
                )
                tx.add(message)
                tx.flush()
                for item in extraction.observations:
                    if item.feature_id is not None and item.feature_id not in self._bundle.feature_ids():
                        continue  # a provider may only return concepts from the supplied vocabulary
                    prior = by_feature.get(item.feature_id) if item.feature_id else None
                    new_rows.append(
                        SessionObservation(
                            observation_id=uuid.uuid4(),
                            session_id=session_id,
                            message_id=message.message_id,
                            feature_id=item.feature_id,
                            raw_phrase_encrypted=self._cipher.encrypt(item.text),
                            presence=item.presence,
                            confirmed=False,
                            observation_version=version,
                            modifiers={
                                "span": [item.start, item.end],
                                "experiencer": item.experiencer,
                                "extractor": extraction.extractor_version,
                            },
                            supersedes=prior.observation_id if prior else None,
                        )
                    )
            else:
                assert payload.observations is not None
                seen_features: set[str] = set()
                superseding: set[uuid.UUID] = set()
                for given in payload.observations:
                    if given.feature_id not in self._bundle.feature_ids():
                        raise ApiError(422, "unknown_feature", "An observation refers to an unknown concept.")
                    if given.feature_id in seen_features:
                        raise ApiError(422, "duplicate_feature", "A concept appears more than once in this request.")
                    seen_features.add(given.feature_id)
                    target = None
                    if given.supersedes is not None:
                        target = by_id.get(given.supersedes)
                        # Unknown, already-superseded or other-session targets are all rejected alike.
                        if target is None or given.supersedes in superseding:
                            raise ApiError(
                                422,
                                "invalid_supersedes",
                                "The observation being corrected is not a current observation of this session.",
                            )
                        superseding.add(given.supersedes)
                    existing = by_feature.get(given.feature_id)
                    if existing is not None and (target is None or existing.observation_id != target.observation_id):
                        raise ApiError(
                            422,
                            "supersedes_required",
                            "This concept already has a current observation; correct it by superseding it.",
                        )
                    modifiers = {
                        k: v
                        for k, v in (
                            ("onset", given.onset),
                            ("duration", given.duration),
                            ("severity", given.severity),
                        )
                        if v is not None
                    }
                    new_rows.append(
                        SessionObservation(
                            observation_id=uuid.uuid4(),
                            session_id=session_id,
                            feature_id=given.feature_id,
                            raw_phrase_encrypted=target.raw_phrase_encrypted if target else None,
                            presence=given.presence,
                            value=given.value,
                            modifiers=modifiers,
                            confirmed=given.confirmed,
                            observation_version=0,
                            supersedes=given.supersedes,
                        )
                    )
                version = self._bump(tx, session, payload.observation_version)
                for row in new_rows:
                    row.observation_version = version
            tx.add_all(new_rows)
            tx.flush()
            current = self._current(tx, session_id)
            session.state = self._state_after_change(
                session.state, self._facts(current, session.demographics, confirmed_only=False)
            )
            self._audit(
                tx,
                principal,
                session_id,
                "observations_submitted",
                observation_version=version,
                count=len(new_rows),
                mode="text" if payload.text is not None else "structured",
                state=session.state,
            )
            return self._session_out(session, current), session_id

        return self._idempotent(
            principal, idempotency_key, "submit_observations", session_id, payload.model_dump(mode="json"), fn
        )

    def submit_answer(
        self, principal: Principal, session_id: uuid.UUID, payload: sc.AnswerSubmit, idempotency_key: str
    ) -> dict[str, Any]:
        principal.require_scope("assessment:write")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            session = self._load(tx, principal, session_id, lock=True)
            if session.observation_version != payload.observation_version:
                raise stale_version(session.observation_version)
            current = self._current(tx, session_id)
            facts = self._facts(current, session.demographics, confirmed_only=False)
            screening = screen(self._bundle, facts)
            if session.state in _PAUSED_STATES or screening.escalation or screening.scope_exclusion:
                raise ApiError(409, "questioning_paused", "Follow-up questions are paused for this session.")
            question = self._bundle.question(payload.question_id)
            if question is None:
                raise ApiError(422, "unknown_question", "This question is not part of the current question set.")
            expected = next_question(self._bundle, facts)
            if expected is None or expected.question_id != question.question_id:
                # An answer is only accepted for the question the server would ask right now.
                raise ApiError(
                    409,
                    "question_not_current",
                    "This question is no longer current. Refresh and answer the current question.",
                )
            try:
                outcome = interpret_answer(question.answer_schema, payload.answer, question.option_presence)
            except AnswerValidationError as exc:
                raise ApiError(422, "invalid_answer", f"The answer is not valid for this question: {exc}.") from exc
            version = self._bump(tx, session, payload.observation_version)
            tx.add(
                SessionAnswer(
                    answer_id=uuid.uuid4(),
                    session_id=session_id,
                    question_id=question.question_id,
                    value=payload.answer,
                    observation_version=version,
                )
            )
            prior = next((o for o in current if o.feature_id == question.feature_id), None)
            tx.add(
                SessionObservation(
                    observation_id=uuid.uuid4(),
                    session_id=session_id,
                    feature_id=question.feature_id,
                    presence=outcome.presence,
                    value=outcome.value,
                    modifiers={"duration": outcome.duration} if outcome.duration else {},
                    raw_phrase_encrypted=self._cipher.encrypt(outcome.raw_phrase) if outcome.raw_phrase else None,
                    confirmed=True,
                    observation_version=version,
                    supersedes=prior.observation_id if prior else None,
                )
            )
            tx.flush()
            current = self._current(tx, session_id)
            session.state = self._state_after_change(
                session.state, self._facts(current, session.demographics, confirmed_only=False)
            )
            self._audit(
                tx,
                principal,
                session_id,
                "answer_submitted",
                observation_version=version,
                question_id=question.question_id,
                state=session.state,
            )
            return self._session_out(session, current), session_id

        return self._idempotent(
            principal, idempotency_key, "submit_answer", session_id, payload.model_dump(mode="json"), fn
        )

    def get_next_question(
        self, principal: Principal, session_id: uuid.UUID, observation_version: int
    ) -> dict[str, Any] | None:
        principal.require_scope("assessment:read")
        with self._db.transaction(principal.subject) as tx:
            session = self._load(tx, principal, session_id)
            if session.observation_version != observation_version:
                raise stale_version(session.observation_version)
            facts = self._facts(self._current(tx, session_id), session.demographics, confirmed_only=False)
            screening = screen(self._bundle, facts)
            if session.state in _PAUSED_STATES or screening.escalation or screening.scope_exclusion:
                return None  # routine questioning stops; never gate escalation on a questionnaire
            question = next_question(self._bundle, facts)
            if question is None:
                return None
            return sc.dump(
                sc.QuestionOut(
                    question_id=question.question_id,
                    wording=question.wording,
                    answer_schema=question.answer_schema,
                    observation_version=session.observation_version,
                )
            )

    def assess_session(
        self, principal: Principal, session_id: uuid.UUID, payload: sc.AssessmentRequest, idempotency_key: str
    ) -> dict[str, Any]:
        principal.require_scope("assessment:write")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            session = self._load(tx, principal, session_id, lock=True)
            if session.observation_version != payload.observation_version:
                raise stale_version(session.observation_version)
            current = self._current(tx, session_id)
            all_facts = self._facts(current, session.demographics, confirmed_only=False)
            templates = self._bundle.templates
            unknowns: list[str] = []
            if any(o.feature_id is None for o in current):
                unknowns.append("Some of what you wrote could not be matched to a reviewed concept.")
            for o in current:
                feature = self._bundle.feature(o.feature_id) if o.feature_id else None
                if feature and o.presence == "uncertain":
                    unknowns.append(f"Not sure: {feature.preferred_name}")
            candidates: list[sc.Candidate] = []
            evidence: list[sc.Evidence] = []
            urgency = "not_assessed"
            screening = screen(self._bundle, all_facts)  # always first, on unconfirmed details too
            if screening.escalation:
                action = screening.escalation.action
                status, state, urgency = "urgent_handoff", "urgent_handoff", action.urgency or "urgent"
                next_action = sc.NextAction(type="seek_care", text=action.text)
            elif screening.scope_exclusion:
                status = state = "out_of_scope"
                next_action = sc.NextAction(type="show_summary", text=screening.scope_exclusion.action.text)
            elif any(o.feature_id and not o.confirmed for o in current):
                status, state = "needs_clarification", "clarifying"
                next_action = sc.NextAction(type="ask_question", text=templates.confirm_details)
            elif (question := next_question(self._bundle, all_facts)) is not None:
                status, state = "needs_clarification", "clarifying"
                next_action = sc.NextAction(
                    type="ask_question", text=question.wording, question_id=question.question_id
                )
            else:
                confirmed = self._facts(current, session.demographics, confirmed_only=True)
                try:
                    matches = self._candidates.candidates(confirmed)
                    found = self._evidence.get_many(sorted({e for m in matches for e in m.evidence_ids}))
                except Exception as exc:  # provider outage: abstain, never guess
                    raise _ProviderFailure() from exc
                withheld = 0
                for match in matches:
                    if not all(e in found for e in match.evidence_ids):
                        withheld += 1  # no evidence, no claim
                        continue
                    if len(candidates) == 3:
                        break
                    candidates.append(
                        sc.Candidate(
                            disease_id=match.disease_id,
                            name=match.name,
                            explanation=match.explanation,
                            evidence_ids=list(match.evidence_ids),
                            supporting_observation_ids=[
                                o.observation_id
                                for o in current
                                if o.confirmed and o.feature_id in match.supporting_features
                            ],
                            conflicting_observation_ids=[
                                o.observation_id
                                for o in current
                                if o.confirmed and o.feature_id in match.conflicting_features
                            ],
                        )
                    )
                    for e in match.evidence_ids:
                        if all(x.evidence_id != e for x in evidence):
                            r = found[e]
                            evidence.append(
                                sc.Evidence(
                                    evidence_id=r.evidence_id,
                                    source_title=r.source_title,
                                    source_url=r.source_url,
                                    excerpt=r.excerpt,
                                    knowledge_release=r.knowledge_release,
                                )
                            )
                if withheld:
                    unknowns.append(
                        "A possible explanation was withheld because its supporting evidence is unavailable."
                    )
                if candidates:
                    status, state = "provisional", "result_ready"
                    next_action = sc.NextAction(type="show_summary", text=templates.provisional_next_step)
                else:
                    status = state = "insufficient_information"
                    next_action = sc.NextAction(type="show_summary", text=templates.insufficient_information)
            out = sc.AssessmentOut(
                assessment_id=uuid.uuid4(),
                session_id=session_id,
                observation_version=session.observation_version,
                status=status,  # type: ignore[arg-type]  # Literal membership is validated by the model
                urgency=urgency,  # type: ignore[arg-type]
                candidates=candidates,
                unknowns=unknowns,
                next_action=next_action,
                evidence_ids=[e.evidence_id for e in evidence],
                versions=sc.Versions(
                    knowledge=self._bundle.knowledge_version,
                    rules=self._bundle.rules_version,
                    model=None,
                    prompt=self._extractor.version,
                ),
                evidence=evidence,
            )
            body = sc.dump(out)
            tx.add(
                Assessment(
                    assessment_id=out.assessment_id,
                    session_id=session_id,
                    observation_version=out.observation_version,
                    status=status,
                    urgency=urgency,
                    candidates=body["candidates"],
                    unknowns=unknowns,
                    evidence_ids=body["evidence_ids"],
                    knowledge_release_id=self._bundle.knowledge_release_id,
                    rule_bundle_id=self._bundle.bundle_id,
                    prompt_version=self._extractor.version,
                    next_action=body["next_action"],
                )
            )
            session.state = state
            self._audit(
                tx,
                principal,
                session_id,
                "assessment_created",
                observation_version=out.observation_version,
                status=status,
                urgency=urgency,
                candidate_count=len(candidates),
            )
            return body, session_id

        try:
            return self._idempotent(
                principal, idempotency_key, "assess_session", session_id, payload.model_dump(mode="json"), fn
            )
        except _ProviderFailure:
            with self._db.transaction(principal.subject) as tx:
                tx.execute(
                    update(Session)
                    .where(
                        Session.session_id == session_id,
                        Session.owner_subject == principal.subject,
                        Session.deleted_at.is_(None),
                    )
                    .values(state="system_unavailable")
                )
            raise ApiError(
                503, "assessment_unavailable", self._bundle.templates.system_unavailable, retryable=True
            ) from None

    def create_summary(
        self, principal: Principal, session_id: uuid.UUID, payload: sc.AssessmentRequest, idempotency_key: str
    ) -> dict[str, Any]:
        principal.require_scope("assessment:export")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            session = self._load(tx, principal, session_id)
            if session.observation_version != payload.observation_version:
                raise stale_version(session.observation_version)
            current = self._current(tx, session_id)
            answers = list(
                tx.execute(
                    select(SessionAnswer)
                    .where(SessionAnswer.session_id == session_id)
                    .order_by(SessionAnswer.observation_version)
                ).scalars()
            )
            latest = tx.execute(
                select(Assessment)
                .where(Assessment.session_id == session_id)
                .order_by(Assessment.observation_version.desc(), Assessment.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            text = self._summary_text(session, current, answers, latest)
            self._audit(tx, principal, session_id, "summary_created", observation_version=session.observation_version)
            return sc.dump(
                sc.SummaryOut(session_id=session_id, observation_version=session.observation_version, summary_text=text)
            ), session_id

        return self._idempotent(
            principal, idempotency_key, "create_summary", session_id, payload.model_dump(mode="json"), fn
        )

    def _summary_text(
        self,
        session: Session,
        current: list[SessionObservation],
        answers: list[SessionAnswer],
        latest: Assessment | None,
    ) -> str:
        def describe(o: SessionObservation) -> str:
            feature = self._bundle.feature(o.feature_id) if o.feature_id else None
            name = feature.preferred_name if feature else "Unmatched detail"
            phrase = self._cipher.decrypt(o.raw_phrase_encrypted) if o.raw_phrase_encrypted else None
            parts = [name]
            if phrase:
                parts.append(f'(in your words: "{phrase}")')
            mods = o.modifiers or {}
            parts += [f"{k}: {mods[k]}" for k in ("onset", "duration", "severity") if mods.get(k)]
            if o.value is not None:
                parts.append(f"value: {json.dumps(o.value)}")
            if not o.confirmed:
                parts.append("[not yet confirmed by you]")
            return "- " + " ".join(parts)

        def section(title: str, rows: list[str]) -> list[str]:
            return [title, *(rows or ["- None recorded"]), ""]

        lines = ["Feeltriva consultation summary"]
        if self._bundle.synthetic:
            lines.append("SAMPLE INFORMATION - synthetic fixture mode - not a medical assessment")
        lines += [f"Prepared: {self._now().date().isoformat()}", ""]
        demo = session.demographics or {}
        context = (
            [f"- Age: {demo['age_years']} years"] if demo.get("age_years") is not None else ["- Age: not provided"]
        )
        if demo.get("gender_identity"):
            context.append(f"- Gender identity (self-described): {demo['gender_identity']}")
        lines += section("Context", context)
        lines += section("Reported by you", [describe(o) for o in current if o.presence == "present"])
        lines += section("Explicitly not present", [describe(o) for o in current if o.presence == "absent"])
        lines += section(
            "Unclear or needing clarification", [describe(o) for o in current if o.presence == "uncertain"]
        )
        answer_rows = []
        for a in answers:
            q = self._bundle.question(a.question_id)
            answer_rows.append(f"- {q.wording if q else a.question_id} Answer: {json.dumps(a.value)}")
        lines += section("Follow-up answers", answer_rows)
        if latest is not None and latest.observation_version == session.observation_version:
            lines += section("Next step from the latest assessment", [f"- {latest.next_action.get('text', '')}"])
            if latest.candidates:
                lines += section(
                    "Provisional possible explanations (not a diagnosis)",
                    [f"- {c['name']}" for c in latest.candidates],
                )
            if latest.unknowns:
                lines += section("Still uncertain", [f"- {u}" for u in latest.unknowns])
        else:
            lines += section("Assessment", ["- No assessment is available for the current details."])
        lines.append(
            "This summary contains information reported by the user. It is not a diagnosis. "
            "Details not mentioned were not assessed and are not assumed to be absent."
        )
        return "\n".join(lines)

    def delete_session(self, principal: Principal, session_id: uuid.UUID, idempotency_key: str) -> dict[str, Any]:
        principal.require_scope("assessment:delete")

        def fn(tx: Tx) -> tuple[dict[str, Any], uuid.UUID]:
            session = self._load(tx, principal, session_id, lock=True, allow_expired=True)
            receipt_id = f"del_{uuid.uuid4().hex}"
            for model in (SessionAnswer, Assessment, SessionObservation, SessionMessage):
                tx.execute(delete(model).where(model.session_id == session_id))
            # Earlier replay records hold encrypted health content; this request's own record
            # is not linked to the session yet, so it survives and will only hold the receipt.
            tx.execute(delete(IdempotencyKey).where(IdempotencyKey.session_id == session_id))
            session.demographics = {}
            session.state = "closed"
            session.deleted_at = self._now()
            self._audit(tx, principal, session_id, "session_deleted", receipt_id=receipt_id)
            # Primary-store content is removed in this transaction. Backups, traces and object
            # storage have no purge job or retention policy yet, so completion is not claimed.
            return sc.dump(
                sc.DeletionReceipt(session_id=session_id, status="deletion_scheduled", receipt_id=receipt_id)
            ), session_id

        return self._idempotent(principal, idempotency_key, "delete_session", session_id, None, fn)
