"""Clinically relevant context (M3.9), on the synthetic rule set: a context question is asked only when its rule
says it applies, never because of the self-described gender; "prefer not to answer" is always an answer; the
answer is kept apart from what the person reports and apart from the gender."""

from __future__ import annotations

import copy
import json

import pytest
from feeltriva_clinical import BundleError, load_fixture_bundle, validate_bundle
from feeltriva_clinical.bundle import FIXTURE_PATH, ReleaseBundle

from tests.conftest import DEFAULT_ANSWERS, Api

CONTEXT = "fx.q.context"
ZETA = "fx.context_zeta"


def _asked(api: Api, text: str, demographics: dict, context_answer="yes"):
    """A whole conversation: the questions in the order they were asked, and the session at the end."""
    session = api.start(demographics).json()
    session = api.confirm_all(api.text(session["session_id"], 0, text).json())
    asked, schemas = [], {}
    while (r := api.next_question(session["session_id"], session["observation_version"])).status_code == 200:
        question = r.json()
        asked.append(question["question_id"])
        schemas[question["question_id"]] = question["answer_schema"]
        answer = context_answer if question["question_id"] == CONTEXT else DEFAULT_ANSWERS[question["question_id"]]
        r = api.answer(session["session_id"], session["observation_version"], question["question_id"], answer)
        assert r.status_code == 200, r.text
        session = r.json()
    return asked, session, schemas


def test_a_context_question_is_asked_only_when_its_rule_applies_and_never_because_of_gender(api: Api):
    plain, with_detail = {}, {}
    for gender in (None, "woman", "man", "non-binary", "prefer to self-describe: sample"):
        demographics = {"age_years": 30, **({"gender_identity": gender} if gender else {})}
        plain[gender], _session, _schemas = _asked(api, "I have alpha", demographics)
        with_detail[gender], _session, _schemas = _asked(api, "I have alpha and epsilon", demographics)
    # Without the detail its rule names, the context question is never asked, whatever the gender.
    assert set(map(tuple, plain.values())) == {("fx.q.beta", "fx.q.gamma", "fx.q.delta", "fx.q.duration")}
    # With it, the question is asked, and at the same place for everybody.
    assert len(set(map(tuple, with_detail.values()))) == 1
    assert CONTEXT in with_detail[None] and with_detail[None].count(CONTEXT) == 1  # and once


def test_the_answer_is_kept_as_context_apart_from_what_is_reported_and_from_gender(api: Api):
    asked, session, schemas = _asked(api, "I have alpha and epsilon", {"age_years": 30, "gender_identity": "woman"})
    # The question itself says that "prefer not to answer" is offered; an ordinary question does not.
    assert schemas[CONTEXT]["allow_prefer_not_to_answer"] is True
    assert "allow_prefer_not_to_answer" not in schemas["fx.q.beta"]
    kept = session["demographics"]["clinically_relevant_context"][ZETA]
    assert (kept["presence"], kept["prefer_not_to_answer"], kept["question_id"]) == ("present", False, CONTEXT)
    assert session["demographics"]["gender_identity"] == "woman"
    assert ZETA not in {o["feature_id"] for o in session["observations"]}
    text = api.summary(session["session_id"], session["observation_version"]).json()["summary_text"]
    context_part = text.split("Context")[1].split("Reported by you")[0]
    assert "Fixture context factor zeta (sample): Yes" in context_part
    assert "Gender identity (self-described): woman" in context_part
    assert "Fixture context factor zeta" not in text.split("Reported by you")[1].split("Follow-up answers")[0]


def test_prefer_not_to_answer_is_always_an_answer_to_a_context_question_and_to_no_other(api: Api):
    asked, session, _schemas = _asked(
        api, "I have alpha and epsilon", {"age_years": 30}, context_answer="prefer_not_to_answer"
    )
    kept = session["demographics"]["clinically_relevant_context"][ZETA]
    # The fact stays unknown, the question is not asked again, and the conversation went on to its end.
    assert (kept["presence"], kept["prefer_not_to_answer"], kept.get("value")) == ("uncertain", True, None)
    assert asked.count(CONTEXT) == 1 and len(asked) == 5
    assert api.next_question(session["session_id"], session["observation_version"]).status_code == 204
    text = api.summary(session["session_id"], session["observation_version"]).json()["summary_text"]
    assert "Fixture context factor zeta (sample): Prefer not to answer" in text
    assert "Answer: Prefer not to answer" in text

    # An ordinary question does not take it.
    other = api.start({"age_years": 30}).json()
    other = api.confirm_all(api.text(other["session_id"], 0, "I have alpha").json())
    question = api.next_question(other["session_id"], other["observation_version"]).json()
    refused = api.answer(
        other["session_id"], other["observation_version"], question["question_id"], "prefer_not_to_answer"
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "invalid_answer")


def test_context_sent_by_the_caller_for_another_item_is_not_read_as_an_answer(api: Api):
    # The contract lets a caller send context when a session starts. Only an answer in the service's own form to
    # a context question of the rule set counts; anything else is kept as sent and decides nothing.
    session = api.start(
        {"age_years": 30, "clinically_relevant_context": {"fx.signal_beta": {"presence": "present"}, "note": "x"}}
    ).json()
    session = api.confirm_all(api.text(session["session_id"], 0, "I have alpha").json())
    first = api.next_question(session["session_id"], session["observation_version"]).json()
    assert first["question_id"] == "fx.q.beta"  # still asked: the context did not answer it


def test_a_context_question_needs_a_rule_and_an_answer_beside_which_declining_can_be_offered():
    fixture = json.loads(FIXTURE_PATH.read_text())
    assert load_fixture_bundle().question(CONTEXT).stores == "context"

    def changed(**fields) -> ReleaseBundle:
        raw = copy.deepcopy(fixture)
        question = next(q for q in raw["questions"] if q["question_id"] == CONTEXT)
        for key, value in fields.items():
            if value is None:
                question.pop(key, None)
            else:
                question[key] = value
        return ReleaseBundle.model_validate(raw)

    with pytest.raises(BundleError, match="no rule that says when it applies"):
        validate_bundle(changed(applicability=None), clinical_mode=False)
    with pytest.raises(BundleError, match="yes or no or with one choice"):
        validate_bundle(changed(answer_schema={"type": "number"}), clinical_mode=False)
    with pytest.raises(BundleError, match="prefer_not_to_answer"):
        options = [{"value": "prefer_not_to_answer", "label": "x"}, {"value": "a", "label": "A"}]
        validate_bundle(changed(answer_schema={"type": "single_choice", "options": options}), clinical_mode=False)
    # A rule cannot name the gender at all: the only field of a person a rule may read is the age.
    with pytest.raises(BundleError):
        gender_rule = {"op": "compare", "field": "demographics.gender_identity", "cmp": "eq", "value": 1}
        validate_bundle(changed(applicability=gender_rule), clinical_mode=False)
