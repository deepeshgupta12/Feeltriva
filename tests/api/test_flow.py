"""End-to-end fixture-mode flows through the REST transport (synthetic, nonmedical concepts)."""

from __future__ import annotations

import uuid

from feeltriva_api.container import build_container
from feeltriva_api.main import create_app
from feeltriva_llm import UnavailableExtractor
from starlette.testclient import TestClient

from tests.conftest import DEFAULT_ANSWERS, Api


def _by_feature(session):
    return {o["feature_id"]: o for o in session["observations"]}


def _to_result(api: Api, text: str = "I have alpha", answers=DEFAULT_ANSWERS, demographics=None):
    session = api.start(demographics or {"age_years": 30}).json()
    session = api.text(session["session_id"], 0, text).json()
    session = api.confirm_all(session)
    session = api.answer_all(session, answers)
    return session, api.assess(session["session_id"], session["observation_version"]).json()


def test_normal_flow_intake_confirm_followup_result_summary(api: Api):
    r = api.start({"age_years": 30, "gender_identity": "non-binary"})
    assert r.status_code == 201
    session = r.json()
    sid = session["session_id"]
    assert (session["state"], session["observation_version"], session["observations"]) == ("intake", 0, [])

    session = api.text(sid, 0, "I have alpha since yesterday").json()
    alpha = _by_feature(session)["fx.signal_alpha"]
    assert session["state"] == "clarifying" and session["observation_version"] == 1
    assert (alpha["presence"], alpha["confirmed"], alpha["raw_phrase"]) == ("present", False, "alpha")

    # Unconfirmed interpretation: the server asks for confirmation rather than assessing on it.
    pending = api.assess(sid, 1).json()
    assert pending["status"] == "needs_clarification" and pending["candidates"] == []

    session = api.confirm_all(session)
    confirmed = _by_feature(session)["fx.signal_alpha"]
    assert confirmed["confirmed"] and confirmed["supersedes"] == alpha["observation_id"]
    assert confirmed["raw_phrase"] == "alpha"  # the user's own wording survives the correction chain

    asked = []
    while (r := api.next_question(sid, session["observation_version"])).status_code == 200:
        question = r.json()
        asked.append(question["question_id"])
        assert question["observation_version"] == session["observation_version"]
        session = api.answer(
            sid, session["observation_version"], question["question_id"], DEFAULT_ANSWERS[question["question_id"]]
        ).json()
    assert r.status_code == 204 and r.content == b""
    assert asked == ["fx.q.beta", "fx.q.gamma", "fx.q.delta", "fx.q.duration"]  # one at a time, no repeats
    assert _by_feature(session)["fx.signal_gamma"]["presence"] == "absent"  # explicit "none of these"

    result = api.assess(sid, session["observation_version"]).json()
    assert result["status"] == "provisional"
    assert result["urgency"] == "not_assessed"  # no approved urgency content: never implied as low
    assert [c["name"] for c in result["candidates"]] == ["Illustrative possibility A"]
    candidate = result["candidates"][0]
    assert set(candidate) == {
        "disease_id",
        "name",
        "supporting_observation_ids",
        "conflicting_observation_ids",
        "evidence_ids",
        "explanation",
    }  # no probability or score field exists
    assert {e["evidence_id"] for e in result["evidence"]} == set(candidate["evidence_ids"]) == {"fx.ev.1"}
    supporting = {
        o["observation_id"] for o in session["observations"] if o["feature_id"] in ("fx.signal_alpha", "fx.signal_beta")
    }
    assert set(candidate["supporting_observation_ids"]) == supporting
    assert result["versions"] == {
        "knowledge": "fixture-knowledge-0",
        "rules": "fixture-rules-0",
        "model": None,
        "prompt": "fixture-extractor-0",
    }
    assert api.get(sid).json()["state"] == "result_ready"

    summary = api.summary(sid, session["observation_version"]).json()
    text = summary["summary_text"]
    assert summary["requires_user_review"] is True
    assert "SAMPLE INFORMATION" in text and "not a diagnosis" in text
    reported, negatives = text.split("Explicitly not present")
    assert "Fixture signal alpha" in reported and "Fixture signal gamma" in negatives.split("Unclear")[0]
    # M3.14a: what was answered is said in words. No stored internal value, no raw JSON, and nothing said twice.
    assert "value:" not in text and '{"' not in text and '"none"' not in text
    assert "Fixture signal gamma (sample) answer: None of these" in negatives.split("Unclear")[0]
    lasting = [line for line in text.splitlines() if "duration: 3 days" in line]
    assert len(lasting) == 1 and lasting[0].count("3 days") == 1 and "answer:" not in lasting[0]
    answers_part = text.split("Follow-up answers")[1].split("Next step")[0]
    assert "Answer: Yes" in answers_part and "Answer: None of these" in answers_part
    assert "Answer: 5 sample units" in answers_part and "Answer: 3 days" in answers_part


def test_correction_invalidates_result_and_recomputes(api: Api):
    session, result = _to_result(api)
    sid, version = session["session_id"], session["observation_version"]
    assert result["status"] == "provisional"

    beta = _by_feature(session)["fx.signal_beta"]
    session = api.observe(
        sid,
        version,
        [
            {
                "feature_id": "fx.signal_beta",
                "presence": "absent",
                "confirmed": True,
                "supersedes": beta["observation_id"],
            }
        ],
    ).json()
    assert session["observation_version"] == version + 1
    assert session["state"] == "assessing"  # completed result moved back, not left as result_ready
    assert _by_feature(session)["fx.signal_beta"]["presence"] == "absent"
    assert len([o for o in session["observations"] if o["feature_id"] == "fx.signal_beta"]) == 1

    # The old result's version can no longer be assessed or summarised.
    assert api.assess(sid, version).status_code == 409
    assert api.summary(sid, version).status_code == 409

    # delta was only applicable while beta was present; nothing new is asked, and A no longer fits.
    fresh = api.assess(sid, version + 1).json()
    assert fresh["observation_version"] == version + 1
    assert fresh["status"] == "insufficient_information" and fresh["candidates"] == []
    assert fresh["assessment_id"] != result["assessment_id"]


def test_urgent_marker_escalates_immediately_and_stops_routine_questions(api: Api):
    sid = api.start({"age_years": 40}).json()["session_id"]
    session = api.text(sid, 0, "alpha and the escalation marker")
    assert session.json()["state"] == "urgent_handoff"  # on the raw message, before any confirmation
    assert api.next_question(sid, 1).status_code == 204
    paused = api.answer(sid, 1, "fx.q.beta", "yes")
    assert paused.status_code == 409 and paused.json()["code"] == "questioning_paused"
    result = api.assess(sid, 1).json()
    assert (result["status"], result["urgency"], result["next_action"]["type"]) == (
        "urgent_handoff",
        "urgent",
        "seek_care",
    )
    assert result["candidates"] == [] and result["evidence"] == []
    assert "synthetic fixture" in result["next_action"]["text"]


def test_user_can_retract_a_misread_escalation(api: Api):
    sid = api.start({"age_years": 40}).json()["session_id"]
    session = api.text(sid, 0, "escalation marker").json()
    marker = _by_feature(session)["fx.escalation_marker"]
    session = api.observe(
        sid,
        1,
        [
            {
                "feature_id": "fx.escalation_marker",
                "presence": "absent",
                "confirmed": True,
                "supersedes": marker["observation_id"],
            }
        ],
    ).json()
    assert session["state"] == "clarifying"
    assert api.next_question(sid, 2).status_code == 200


def test_explicit_negation_is_recorded_and_silence_is_not(api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    seen = _by_feature(api.text(sid, 0, "alpha but no beta").json())
    assert seen["fx.signal_beta"]["presence"] == "absent"
    assert "fx.signal_gamma" not in seen  # never mentioned: unknown, not absent
    assert api.next_question(sid, 1).json()["question_id"] == "fx.q.gamma"  # beta is not re-asked


def test_unmatched_text_is_kept_verbatim_and_flagged_unknown(api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    session = api.text(sid, 0, "something this fixture has no concept for").json()
    only = session["observations"][0]
    assert (only["feature_id"], only["presence"], only["confirmed"]) == (None, "uncertain", False)
    assert only["raw_phrase"] == "something this fixture has no concept for"
    session = api.answer_all(session, {**DEFAULT_ANSWERS, "fx.q.beta": "no"})
    result = api.assess(sid, session["observation_version"]).json()
    assert result["status"] == "insufficient_information"
    assert result["urgency"] == "not_assessed"
    assert any("could not be matched" in u for u in result["unknowns"])
    assert "not a sign that everything is fine" in result["next_action"]["text"]


def test_candidate_without_resolvable_evidence_is_withheld(api: Api):
    answers = {**DEFAULT_ANSWERS, "fx.q.beta": "no", "fx.q.gamma": "option_one"}
    session, result = _to_result(api, answers=answers)
    # Possibility B's condition holds (alpha + gamma) but its only citation does not exist.
    assert result["status"] == "insufficient_information" and result["candidates"] == []
    assert result["evidence"] == [] and result["evidence_ids"] == []
    assert any("withheld" in u for u in result["unknowns"])
    assert api.get(session["session_id"]).json()["state"] == "insufficient_information"


def test_not_sure_answer_is_uncertain_and_blocks_the_dependent_candidate(api: Api):
    session, result = _to_result(api, answers={**DEFAULT_ANSWERS, "fx.q.beta": "not_sure"})
    assert _by_feature(session)["fx.signal_beta"]["presence"] == "uncertain"
    assert result["candidates"] == [] and any(u.startswith("Not sure:") for u in result["unknowns"])


def test_minor_is_out_of_scope_but_escalation_still_wins(api: Api):
    session = api.start({"age_years": 16}).json()
    sid = session["session_id"]
    assert session["state"] == "out_of_scope"
    assert api.next_question(sid, 0).status_code == 204
    result = api.assess(sid, 0).json()
    assert (result["status"], result["urgency"], result["candidates"]) == ("out_of_scope", "not_assessed", [])
    # Scope exclusion does not disable safety screening.
    assert api.text(sid, 0, "escalation marker").json()["state"] == "urgent_handoff"
    assert api.assess(sid, 1).json()["status"] == "urgent_handoff"


def test_age_not_provided_is_not_treated_as_out_of_scope(api: Api):
    assert api.start().json()["state"] == "intake"
    assert api.start({}).json()["state"] == "intake"


def test_provider_outage_yields_503_and_never_a_result(settings, db, api: Api):
    class Down:
        def candidates(self, confirmed):
            raise TimeoutError("provider down")

    container = build_container(settings, db)
    container.assessments._candidates = Down()
    broken = Api(TestClient(create_app(settings, container), raise_server_exceptions=False), subject=api.subject)
    session = api.start({"age_years": 30}).json()
    session = api.confirm_all(api.text(session["session_id"], 0, "alpha").json())
    session = api.answer_all(session, DEFAULT_ANSWERS)
    sid, version = session["session_id"], session["observation_version"]

    key = uuid.uuid4().hex
    r = broken.assess(sid, version, key=key)
    assert r.status_code == 503
    body = r.json()
    assert (body["code"], body["retryable"]) == ("assessment_unavailable", True)
    assert "Nothing has been concluded" in body["message"]
    assert api.get(sid).json()["state"] == "system_unavailable"
    # The failure is not cached against the key: the same request succeeds once the provider is back.
    recovered = api.assess(sid, version, key=key)
    assert recovered.status_code == 200 and recovered.json()["status"] == "provisional"


def test_extraction_outage_saves_nothing(settings, db, api: Api):
    container = build_container(settings, db)
    container.assessments._extractor = UnavailableExtractor()
    broken = Api(TestClient(create_app(settings, container), raise_server_exceptions=False), subject=api.subject)
    sid = api.start({"age_years": 30}).json()["session_id"]
    r = broken.text(sid, 0, "alpha")
    assert r.status_code == 503 and r.json()["code"] == "extraction_unavailable" and r.json()["retryable"]
    session = api.get(sid).json()
    assert (session["observation_version"], session["observations"], session["state"]) == (0, [], "intake")


def test_details_confirmed_in_one_request_come_back_in_the_order_they_were_given(api: Api, owner_db):
    # BUG-035: two observations written in one request had the same time and no order, so the same flow gave
    # them in either order (seen as REST and MCP disagreeing once in many runs). The wrong order is rare, so the
    # cause is checked itself: every row of one request has its own time, later for each one given later.
    import uuid

    from feeltriva_api.models import SessionObservation
    from sqlalchemy import select

    for _attempt in range(3):
        session = api.start({"age_years": 30}).json()
        session = api.text(session["session_id"], 0, "I have alpha and beta but no gamma").json()
        assert len(session["observations"]) == 3
        wanted = list(reversed(session["observations"]))
        confirmed = api.observe(
            session["session_id"],
            session["observation_version"],
            [
                {
                    "feature_id": o["feature_id"],
                    "presence": o["presence"],
                    "confirmed": True,
                    "supersedes": o["observation_id"],
                }
                for o in wanted
            ],
        ).json()
        assert [o["feature_id"] for o in confirmed["observations"]] == [o["feature_id"] for o in wanted]
        again = api.get(session["session_id"]).json()
        assert [o["observation_id"] for o in again["observations"]] == [
            o["observation_id"] for o in confirmed["observations"]
        ]
        with owner_db.transaction(None, role="migration") as tx:
            rows = tx.execute(
                select(SessionObservation.feature_id, SessionObservation.created_at, SessionObservation.confirmed)
                .where(SessionObservation.session_id == uuid.UUID(session["session_id"]))
                .order_by(SessionObservation.created_at)
            ).all()
        for confirmed_rows in (False, True):  # the three found in the text, then the three confirmed together
            times = [at for _feature, at, flag in rows if flag is confirmed_rows]
            assert len(times) == 3 and len(set(times)) == 3
        assert [feature for feature, _at, flag in rows if flag] == [o["feature_id"] for o in wanted]
