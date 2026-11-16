"""Ownership, idempotency, version, validation and deletion guarantees."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from feeltriva_api.container import build_container
from feeltriva_api.main import create_app
from feeltriva_api.models import (
    Assessment,
    AuditEvent,
    IdempotencyKey,
    Session,
    SessionAnswer,
    SessionMessage,
    SessionObservation,
)
from sqlalchemy import func, select
from starlette.testclient import TestClient

from tests.conftest import DEFAULT_ANSWERS, Api


def _session_with_alpha(api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    return api.confirm_all(api.text(sid, 0, "alpha").json())


# ---- authentication and ownership ------------------------------------------------
def test_requests_without_valid_bearer_are_401(client):
    sid = str(uuid.uuid4())
    for headers in (
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer not-a-dev-token"},
        {"Authorization": "Bearer dev:"},
        {"Authorization": "Bearer dev:has spaces"},
    ):
        r = client.get(f"/v1/sessions/{sid}", headers=headers)
        assert r.status_code == 401 and r.json()["code"] == "unauthenticated"


def test_another_caller_cannot_reach_a_session_on_any_path(api: Api, other: Api):
    session = _session_with_alpha(api)
    sid, version = session["session_id"], session["observation_version"]
    attempts = [
        other.get(sid),
        other.text(sid, version, "beta"),
        other.assess(sid, version),
        other.observe(sid, version, [{"feature_id": "fx.signal_beta", "presence": "present", "confirmed": True}]),
        other.answer(sid, version, "fx.q.beta", "yes"),
        other.next_question(sid, version),
        other.summary(sid, version),
        other.delete(sid),
    ]
    for r in attempts:
        assert r.status_code == 404 and r.json()["code"] == "session_not_found", r.text
    # Indistinguishable from a session that does not exist at all.
    assert other.get(str(uuid.uuid4())).json()["message"] == attempts[0].json()["message"]
    assert api.get(sid).json() == session  # and nothing changed for the owner


def test_owner_subject_in_body_is_rejected_not_trusted(api: Api):
    r = api.client.post(
        "/v1/sessions", headers=api.headers(), json={"consent_version": "c", "owner_subject": "someone-else"}
    )
    assert r.status_code == 422


def test_correction_cannot_target_another_sessions_observation(api: Api, other: Api):
    mine, theirs = _session_with_alpha(api), _session_with_alpha(other)
    foreign = theirs["observations"][0]["observation_id"]
    r = api.observe(
        mine["session_id"],
        mine["observation_version"],
        [{"feature_id": "fx.signal_beta", "presence": "present", "confirmed": True, "supersedes": foreign}],
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_supersedes"
    assert other.get(theirs["session_id"]).json() == theirs


def test_already_superseded_observation_cannot_be_corrected_again(api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    first = api.text(sid, 0, "alpha").json()
    original = first["observations"][0]["observation_id"]
    api.confirm_all(first)
    r = api.observe(
        sid, 2, [{"feature_id": "fx.signal_alpha", "presence": "absent", "confirmed": True, "supersedes": original}]
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_supersedes"


def test_second_observation_for_a_concept_requires_explicit_supersede(api: Api):
    session = _session_with_alpha(api)
    r = api.observe(
        session["session_id"],
        session["observation_version"],
        [{"feature_id": "fx.signal_alpha", "presence": "absent", "confirmed": True}],
    )
    assert r.status_code == 422 and r.json()["code"] == "supersedes_required"


# ---- idempotency -------------------------------------------------------------------
def test_idempotent_replay_returns_the_original_response_once(api: Api, owner_db):
    key = uuid.uuid4().hex
    first, second = api.start({"age_years": 30}, key=key), api.start({"age_years": 30}, key=key)
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    with owner_db.transaction(None) as tx:
        count = tx.execute(
            select(func.count()).select_from(Session).where(Session.owner_subject == f"dev:{api.subject}")
        ).scalar_one()
    assert count == 1

    sid, key = first.json()["session_id"], uuid.uuid4().hex
    a, b = api.text(sid, 0, "alpha", key=key), api.text(sid, 0, "alpha", key=key)
    assert a.json() == b.json() and b.json()["observation_version"] == 1  # replayed, not re-applied


def test_same_key_with_different_payload_is_409(api: Api):
    key = uuid.uuid4().hex
    assert api.start({"age_years": 30}, key=key).status_code == 201
    r = api.start({"age_years": 31}, key=key)
    assert r.status_code == 409 and r.json()["code"] == "idempotency_key_conflict"


def test_same_key_cannot_be_reused_across_operations_or_sessions(api: Api):
    key = uuid.uuid4().hex
    a, b = api.start({"age_years": 30}).json(), api.start({"age_years": 30}).json()
    assert api.assess(a["session_id"], 0, key=key).status_code == 200
    assert api.assess(b["session_id"], 0, key=key).status_code == 409
    assert api.summary(a["session_id"], 0, key=key).status_code == 409


def test_idempotency_keys_are_scoped_per_caller(api: Api, other: Api):
    key = uuid.uuid4().hex
    mine, theirs = api.start({"age_years": 30}, key=key), other.start({"age_years": 30}, key=key)
    assert mine.status_code == theirs.status_code == 201
    assert mine.json()["session_id"] != theirs.json()["session_id"]


def test_missing_or_oversized_idempotency_key_is_400(api: Api):
    r = api.client.post("/v1/sessions", headers=api.headers(None), json={"consent_version": "c"})
    assert r.status_code == 400 and r.json()["code"] == "missing_idempotency_key"
    assert api.start(key="k" * 129).status_code == 400


# ---- observation versions ----------------------------------------------------------
def test_stale_version_is_409_on_every_versioned_path(api: Api):
    session = _session_with_alpha(api)
    sid, current = session["session_id"], session["observation_version"]
    stale = current - 1
    for r in (
        api.text(sid, stale, "beta"),
        api.answer(sid, stale, "fx.q.beta", "yes"),
        api.assess(sid, stale),
        api.summary(sid, stale),
        api.next_question(sid, stale),
        api.assess(sid, current + 5),
        api.observe(sid, stale, [{"feature_id": "fx.signal_beta", "presence": "present", "confirmed": True}]),
    ):
        assert r.status_code == 409 and r.json()["code"] == "stale_observation_version", r.text
    assert api.get(sid).json() == session


def test_answer_is_only_accepted_for_the_current_question(api: Api):
    session = _session_with_alpha(api)
    sid, version = session["session_id"], session["observation_version"]
    assert api.next_question(sid, version).json()["question_id"] == "fx.q.beta"
    r = api.answer(sid, version, "fx.q.gamma", "none")  # a real question, but not the one being asked
    assert r.status_code == 409 and r.json()["code"] == "question_not_current"
    assert api.answer(sid, version, "fx.q.unknown", "yes").json()["code"] == "unknown_question"
    bad = api.answer(sid, version, "fx.q.beta", "perhaps")
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_answer"
    assert api.get(sid).json()["observation_version"] == version  # nothing was attached
    assert api.answer(sid, version, "fx.q.beta", "yes").status_code == 200
    # Answering it again (old question, new version) is refused rather than re-attached.
    assert api.answer(sid, version + 1, "fx.q.beta", "no").json()["code"] == "question_not_current"


# ---- validation and error shape ----------------------------------------------------
def test_validation_errors_use_the_error_schema_and_do_not_echo_input(api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    secret = "PRIVATE-SYMPTOM-TEXT"
    cases = [
        api.client.post(
            f"/v1/sessions/{sid}/observations",
            headers=api.headers(),
            json={"observation_version": 0, "text": secret, "observations": []},
        ),
        api.client.post(
            f"/v1/sessions/{sid}/observations",
            headers=api.headers(),
            json={"observation_version": 0, "text": secret, "extra": secret},
        ),
        api.client.post(f"/v1/sessions/{sid}/observations", headers=api.headers(), json={"observation_version": 0}),
        api.client.post(
            f"/v1/sessions/{sid}/observations", headers=api.headers(), content=b"{not json " + secret.encode()
        ),
        api.client.post(
            "/v1/sessions", headers=api.headers(), json={"consent_version": "c", "demographics": {"age_years": 400}}
        ),
        api.client.post("/v1/sessions", headers=api.headers(), json={"consent_version": ""}),
        api.client.get("/v1/sessions/not-a-uuid", headers=api.headers(None)),
    ]
    for r in cases:
        assert r.status_code == 422, r.text
        body = r.json()
        assert set(body) == {"code", "message", "retryable", "request_id"} and secret not in r.text
        assert r.headers["X-Request-ID"] == body["request_id"]
    r = api.observe(sid, 0, [{"feature_id": "not.in.vocabulary", "presence": "present", "confirmed": True}])
    assert r.status_code == 422 and r.json()["code"] == "unknown_feature"


def test_private_responses_are_not_cacheable(api: Api):
    assert api.start().headers["Cache-Control"] == "no-store"


def test_expired_session_is_refused_but_can_still_be_deleted(settings, db, api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    container = build_container(settings, db)
    container.assessments._now = lambda: datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes + 1)
    later = Api(TestClient(create_app(settings, container), raise_server_exceptions=False), subject=api.subject)
    for r in (later.get(sid), later.text(sid, 0, "alpha"), later.assess(sid, 0), later.next_question(sid, 0)):
        assert r.status_code == 403 and r.json()["code"] == "session_expired"
    assert later.delete(sid).status_code == 200


# ---- deletion ----------------------------------------------------------------------
def test_delete_removes_content_and_returns_an_honest_receipt(api: Api, owner_db):
    session = api.answer_all(_session_with_alpha(api), DEFAULT_ANSWERS)
    sid = session["session_id"]
    api.assess(sid, session["observation_version"])
    api.summary(sid, session["observation_version"])
    key = uuid.uuid4().hex
    r = api.delete(sid, key=key)
    assert r.status_code == 200
    receipt = r.json()
    assert receipt["status"] == "deletion_scheduled"  # backups/traces are not purged yet: not "deleted"
    assert receipt["session_id"] == sid and receipt["receipt_id"].startswith("del_")
    assert api.delete(sid, key=key).json() == receipt  # replay returns the same receipt
    assert api.get(sid).status_code == 404
    assert api.delete(sid).status_code == 404  # a new delete request finds nothing
    assert api.text(sid, session["observation_version"], "beta").status_code == 404

    sid_uuid = uuid.UUID(sid)
    with owner_db.transaction(None) as tx:
        for model in (SessionMessage, SessionObservation, SessionAnswer, Assessment):
            left = tx.execute(select(func.count()).select_from(model).where(model.session_id == sid_uuid)).scalar_one()
            assert left == 0, model.__tablename__
        tombstone = tx.get(Session, sid_uuid)
        assert tombstone.deleted_at is not None and tombstone.demographics == {} and tombstone.state == "closed"
        replays = list(tx.execute(select(IdempotencyKey).where(IdempotencyKey.session_id == sid_uuid)).scalars())
        assert [k.operation for k in replays] == ["delete_session"]  # earlier replay bodies are gone


def test_audit_events_record_actions_without_symptom_text(api: Api, owner_db):
    phrase = "alpha and no beta"
    session = api.confirm_all(api.text(api.start({"age_years": 30}).json()["session_id"], 0, phrase).json())
    with owner_db.transaction(None) as tx:
        events = list(
            tx.execute(select(AuditEvent).where(AuditEvent.session_id == uuid.UUID(session["session_id"]))).scalars()
        )
    assert {e.event_type for e in events} == {"session_started", "observations_submitted"}
    blob = " ".join(str(e.redacted_metadata) for e in events)
    assert "alpha" not in blob and "beta" not in blob and phrase not in blob


def test_free_text_is_encrypted_at_rest(api: Api, owner_db):
    phrase = "alpha-marker-plaintext-check alpha"
    sid = uuid.UUID(api.start({"age_years": 30}).json()["session_id"])
    api.text(str(sid), 0, phrase)
    with owner_db.transaction(None) as tx:
        message = tx.execute(select(SessionMessage).where(SessionMessage.session_id == sid)).scalar_one()
        observation = (
            tx.execute(select(SessionObservation).where(SessionObservation.session_id == sid)).scalars().first()
        )
    assert phrase.encode() not in bytes(message.encrypted_content)
    assert b"alpha" not in bytes(observation.raw_phrase_encrypted)
