"""Session start, observation intake and corrections, follow-up answers and question selection."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from feeltriva_clinical import (
    PREFER_NOT_TO_ANSWER,
    AnswerOutcome,
    AnswerValidationError,
    interpret_answer,
    next_question,
    screen,
)
from feeltriva_llm import ExtractionError
from sqlalchemy.orm import Session as Tx

from . import schemas as sc
from .auth import Principal
from .errors import ApiError, stale_version
from .models import (
    Session,
    SessionAnswer,
    SessionMessage,
    SessionObservation,
)
from .service_core import CONTEXT, PAUSED_STATES, ServiceCore


class IntakeOperations(ServiceCore):
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
            # The rows of one request keep the order they were given in. Left to the database, every row of a
            # transaction gets the same time, and then nothing orders them when the session is read (BUG-035).
            stamp = self._now()
            for position, row in enumerate(new_rows):
                row.created_at = stamp + timedelta(microseconds=position)
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
            if session.state in PAUSED_STATES or screening.escalation or screening.scope_exclusion:
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
            declined = question.stores == "context" and payload.answer == PREFER_NOT_TO_ANSWER
            try:
                # "Prefer not to answer" is always an answer to a context question. It leaves the fact unknown.
                outcome = (
                    AnswerOutcome("uncertain")
                    if declined
                    else interpret_answer(question.answer_schema, payload.answer, question.option_presence)
                )
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
            if question.stores == "context":
                # Kept with the session's context, apart from the observations and from the self-described gender.
                kept = dict((session.demographics or {}).get(CONTEXT) or {})
                kept[question.feature_id] = {
                    "presence": outcome.presence,
                    "value": outcome.value,
                    "prefer_not_to_answer": declined,
                    "question_id": question.question_id,
                    "observation_version": version,
                }
                session.demographics = {**(session.demographics or {}), CONTEXT: kept}
            else:
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
            if session.state in PAUSED_STATES or screening.escalation or screening.scope_exclusion:
                return None  # routine questioning stops; never gate escalation on a questionnaire
            question = next_question(self._bundle, facts)
            if question is None:
                return None
            return sc.dump(
                sc.QuestionOut(
                    question_id=question.question_id,
                    wording=question.wording,
                    # A context question always offers "prefer not to answer"; the question says so itself.
                    answer_schema=(
                        {**question.answer_schema, "allow_prefer_not_to_answer": True}
                        if question.stores == "context"
                        else question.answer_schema
                    ),
                    observation_version=session.observation_version,
                )
            )
