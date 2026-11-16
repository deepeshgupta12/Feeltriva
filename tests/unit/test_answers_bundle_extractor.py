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
