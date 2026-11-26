import copy
import json

import pytest
from feeltriva_api.container import load_release
from feeltriva_api.settings import Settings
from feeltriva_clinical import (
    AnswerValidationError,
    BundleError,
    interpret_answer,
    load_fixture_bundle,
    validate_bundle,
)
from feeltriva_clinical.bundle import FIXTURE_PATH, ReleaseBundle
from feeltriva_llm import MockExtractor, VocabularyTerm

CHOICE = {
    "type": "single_choice",
    "allow_not_sure": True,
    "options": [{"value": "x", "label": "X"}, {"value": "none", "label": "None"}],
}


def test_yes_no_unsure_maps_to_presence_without_guessing():
    schema = {"type": "yes_no_unsure"}
    assert interpret_answer(schema, "yes").presence == "present"
    assert interpret_answer(schema, "no").presence == "absent"
    assert interpret_answer(schema, "not_sure").presence == "uncertain"
    for bad in (True, None, "maybe", ""):
        with pytest.raises(AnswerValidationError):
            interpret_answer(schema, bad)


def test_single_choice_uses_reviewer_mapping_and_rejects_unoffered_options():
    assert interpret_answer(CHOICE, "x").presence == "present"
    assert interpret_answer(CHOICE, "none", {"none": "absent"}).presence == "absent"
    assert interpret_answer(CHOICE, "not_sure").presence == "uncertain"
    with pytest.raises(AnswerValidationError):
        interpret_answer(CHOICE, "y")
    with pytest.raises(AnswerValidationError):
        interpret_answer({**CHOICE, "allow_not_sure": False}, "not_sure")


def test_multiple_choice_rejects_contradictory_selection():
    schema = {"type": "multiple_choice", "options": CHOICE["options"]}
    assert interpret_answer(schema, ["x"]).value == ["x"]
    with pytest.raises(AnswerValidationError):
        interpret_answer(schema, ["x", "none"], {"none": "absent"})
    for bad in ([], ["x", "x"], "x", ["zzz"]):
        with pytest.raises(AnswerValidationError):
            interpret_answer(schema, bad)


def test_number_and_duration_bounds_and_units():
    number = {"type": "number", "unit": "u", "min": 0, "max": 10}
    assert interpret_answer(number, {"value": 3, "unit": "u"}).value == {"value": 3, "unit": "u"}
    for bad in (
        {"value": 11, "unit": "u"},
        {"value": 3, "unit": "kg"},
        {"value": "3", "unit": "u"},
        {"value": True, "unit": "u"},
        3,
        "not_sure",
    ):
        with pytest.raises(AnswerValidationError):
            interpret_answer(number, bad)
    outcome = interpret_answer({"type": "duration"}, {"value": 2, "unit": "weeks"})
    assert (outcome.presence, outcome.duration) == ("present", "2 weeks")
    for bad in ({"value": -1, "unit": "days"}, {"value": 1, "unit": "years"}, {"value": 1}):
        with pytest.raises(AnswerValidationError):
            interpret_answer({"type": "duration"}, bad)


def test_free_text_answer_stays_uncertain():
    outcome = interpret_answer({"type": "free_text"}, "  something  ")
    assert (outcome.presence, outcome.raw_phrase) == ("uncertain", "something")


def test_not_sure_is_one_string_for_every_type_that_allows_it():
    # BUG-010: the web sent ["not_sure"] for multiple choice and the service read "not_sure" on a free-text
    # question as the user's own words. It is one string now, read the same way for every type.
    options = CHOICE["options"]
    for schema in (
        {"type": "multiple_choice", "options": options, "allow_not_sure": True},
        {"type": "free_text", "allow_not_sure": True},
        {"type": "number", "allow_not_sure": True},
        {"type": "duration", "allow_not_sure": True},
        {"type": "date", "allow_not_sure": True},
    ):
        outcome = interpret_answer(schema, "not_sure")
        assert (outcome.presence, outcome.value, outcome.raw_phrase) == ("uncertain", None, None), schema["type"]
    # Where the question does not allow it, it is refused, and the old list form is not an answer.
    for schema in ({"type": "multiple_choice", "options": options}, {"type": "date"}):
        with pytest.raises(AnswerValidationError, match="not allowed"):
            interpret_answer(schema, "not_sure")
    with pytest.raises(AnswerValidationError):
        interpret_answer({"type": "multiple_choice", "options": options, "allow_not_sure": True}, ["not_sure"])
    # On a free-text question that does not offer "not sure", the words stay what the person wrote.
    assert interpret_answer({"type": "free_text"}, "not_sure").raw_phrase == "not_sure"


def test_a_date_answer_is_a_calendar_date_within_the_bounds_of_the_question():
    from datetime import date

    from feeltriva_clinical.answers import validate_answer_schema

    day = date(2026, 3, 10)
    outcome = interpret_answer({"type": "date"}, {"date": "2026-02-28"}, today=day)
    assert (outcome.presence, outcome.value, outcome.duration) == ("present", {"date": "2026-02-28"}, None)
    for bad in (
        "2026-02-28",
        {"date": "28/02/2026"},
        {"date": "2026-02-30"},
        {"date": "2026-2-3"},
        {"date": 20260228},
        {},
        7,
    ):
        with pytest.raises(AnswerValidationError):
            interpret_answer({"type": "date"}, bad, today=day)
    with pytest.raises(AnswerValidationError):
        interpret_answer({"type": "date"}, {"date": "2026-02-28", "time": "10:00"}, today=day)
    # "today" is the day of whoever answers, which can be one day from the service's own: one day is allowed.
    past = {"type": "date", "latest": "today"}
    assert interpret_answer(past, {"date": "2026-03-11"}, today=day).value == {"date": "2026-03-11"}
    with pytest.raises(AnswerValidationError, match="must not be after today"):
        interpret_answer(past, {"date": "2026-03-12"}, today=day)
    # A bound written as a date is exact.
    fixed = {"type": "date", "earliest": "2026-01-01", "latest": "2026-01-31"}
    assert interpret_answer(fixed, {"date": "2026-01-31"}, today=day).presence == "present"
    for outside, words in (("2025-12-31", "before 2026-01-01"), ("2026-02-01", "after 2026-01-31")):
        with pytest.raises(AnswerValidationError, match=words):
            interpret_answer(fixed, {"date": outside}, today=day)
    with pytest.raises(AnswerValidationError, match="must not be before today"):
        interpret_answer({"type": "date", "earliest": "today"}, {"date": "2026-03-08"}, today=day)
    # A question whose bounds make no sense is refused when its bundle is checked.
    validate_answer_schema(fixed)
    validate_answer_schema(past)
    for wrong in (
        {"type": "date", "latest": "soon"},
        {"type": "date", "earliest": "2026-02-01", "latest": "2026-01-01"},
    ):
        with pytest.raises(AnswerValidationError):
            validate_answer_schema(wrong)


def test_fixture_bundle_is_synthetic_pending_and_refused_in_clinical_mode():
    bundle = load_fixture_bundle()
    assert bundle.synthetic and bundle.status == "pending"
    assert all(f.feature_id.startswith("fx.") for f in bundle.features)
    with pytest.raises(BundleError, match="synthetic"):
        validate_bundle(bundle, clinical_mode=True)


def test_clinical_mode_refuses_any_unapproved_item():
    raw = json.loads(FIXTURE_PATH.read_text())
    raw["synthetic"], raw["status"] = False, "approved"
    for group in ("features", "rules", "questions", "candidates", "evidence"):
        for item in raw[group]:
            item["status"] = "approved"
    validate_bundle(ReleaseBundle.model_validate(raw), clinical_mode=True)  # fully approved passes
    one_pending = copy.deepcopy(raw)
    one_pending["rules"][0]["status"] = "pending"
    with pytest.raises(BundleError, match="not approved"):
        validate_bundle(ReleaseBundle.model_validate(one_pending), clinical_mode=True)


def test_bundle_with_unknown_feature_reference_is_rejected():
    raw = json.loads(FIXTURE_PATH.read_text())
    raw["rules"][0]["condition_ast"] = {"op": "present", "feature": "fx.does_not_exist"}
    with pytest.raises(BundleError):
        validate_bundle(ReleaseBundle.model_validate(raw), clinical_mode=False)


def test_settings_guards():
    with pytest.raises(ValueError, match="mock auth"):
        Settings(_env_file=None, app_env="production", auth_mode="mock", session_encryption_key="k")
    with pytest.raises(ValueError, match="SESSION_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            auth_mode="jwt",
            auth_issuer="i",
            auth_audience="a",
            auth_jwks_url="https://example.invalid/jwks",
        )
    with pytest.raises(ValueError, match="clinical mode"):
        Settings(_env_file=None, app_env="test", clinical_mode_enabled=True)
    assert Settings(_env_file=None, app_env="test").clinical_mode_enabled is False  # default OFF


def test_clinical_mode_cannot_start_with_mock_extraction(tmp_path):
    settings = Settings(_env_file=None, app_env="test", clinical_mode_enabled=True, rule_bundle_path=str(FIXTURE_PATH))
    with pytest.raises(RuntimeError, match="mock extraction"):
        load_release(settings)


VOCAB = [
    VocabularyTerm("f.alpha", ("alpha",)),
    VocabularyTerm("f.beta", ("beta",)),
    VocabularyTerm("f.gamma", ("gamma",)),
]


def test_extractor_negation_uncertainty_and_spans():
    text = "I have alpha, no beta. Maybe gamma"
    result = MockExtractor().extract(text, VOCAB)
    by = {o.feature_id: o for o in result.observations}
    assert by["f.alpha"].presence == "present"
    assert by["f.beta"].presence == "absent"
    assert by["f.gamma"].presence == "uncertain"
    for o in result.observations:
        assert text[o.start : o.end] == o.text  # exact source span


def test_extractor_negation_does_not_cross_clause_boundaries():
    result = MockExtractor().extract("no beta, but alpha since Monday", VOCAB)
    by = {o.feature_id: o.presence for o in result.observations}
    assert by == {"f.beta": "absent", "f.alpha": "present"}


def test_extractor_never_invents_absence_and_keeps_unmatched_text():
    result = MockExtractor().extract("  something unrelated  ", VOCAB)
    assert len(result.observations) == 1
    only = result.observations[0]
    assert (only.feature_id, only.presence, only.text) == (None, "uncertain", "something unrelated")
    assert MockExtractor().extract("alphabet soup", VOCAB).observations[0].feature_id is None  # whole words only
