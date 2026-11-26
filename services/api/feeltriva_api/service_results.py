"""Assessment, consultation summary and deletion."""

from __future__ import annotations

import uuid
from typing import Any

from feeltriva_clinical import (
    answer_in_words,
    next_question,
    screen,
)
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as Tx

from . import schemas as sc
from .auth import Principal
from .errors import ApiError, stale_version
from .models import (
    Assessment,
    IdempotencyKey,
    Session,
    SessionAnswer,
    SessionMessage,
    SessionObservation,
)
from .service_core import ProviderFailure, ServiceCore


class ResultOperations(ServiceCore):
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
                    raise ProviderFailure() from exc
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
        except ProviderFailure:
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
            # What was answered, in the words of the question it was answered to: never a stored internal value,
            # and not a second time what the duration above already says (M3.14a).
            asked: list[dict[str, Any] | None] = [
                q.answer_schema for q in self._bundle.questions if q.feature_id == o.feature_id
            ] or [None]
            words = next((said for said in (answer_in_words(schema, o.value) for schema in asked) if said), None)
            if words and words not in {str(mods.get(k)) for k in ("onset", "duration", "severity")}:
                parts.append(f"answer: {words}")
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
            said = answer_in_words(q.answer_schema, a.value) if q else None
            # A question that is no longer in the rule set, or an answer its options no longer hold, is listed
            # without inventing words for it.
            wording = q.wording if q else "A question that is no longer asked."
            answer_rows.append(f"- {wording} Answer: {said or 'recorded, and cannot be shown in words'}")
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
