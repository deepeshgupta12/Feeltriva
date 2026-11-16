import pytest
from feeltriva_clinical import Facts, RuleValidationError, evaluate, validate_ast

F = {"a", "b"}
present_a = {"op": "present", "feature": "a"}
absent_a = {"op": "absent", "feature": "a"}


def test_unknown_feature_satisfies_neither_positive_nor_negative_predicate():
    silent = Facts({})
    assert evaluate(present_a, silent) is None
    assert evaluate(absent_a, silent) is None  # silence is not a denial
    assert evaluate({"op": "not", "arg": present_a}, silent) is None
    assert evaluate({"op": "missing", "feature": "a"}, silent) is True


@pytest.mark.parametrize(
    "state,present,absent",
    [("present", True, False), ("absent", False, True), ("uncertain", None, None), ("not_asked", None, None)],
)
def test_presence_states(state, present, absent):
    facts = Facts({"a": state})
    assert evaluate(present_a, facts) is present
    assert evaluate(absent_a, facts) is absent


def test_kleene_and_or():
    facts = Facts({"a": "present"})  # b unknown
    b = {"op": "present", "feature": "b"}
    assert evaluate({"op": "and", "args": [present_a, b]}, facts) is None
    assert evaluate({"op": "or", "args": [present_a, b]}, facts) is True
    assert evaluate({"op": "and", "args": [absent_a, b]}, facts) is False
    assert evaluate({"op": "or", "args": [absent_a, b]}, facts) is None


def test_numeric_compare_with_missing_value_is_unknown():
    node = {"op": "compare", "field": "demographics.age_years", "cmp": "lt", "value": 18}
    assert evaluate(node, Facts({}, {"demographics.age_years": None})) is None
    assert evaluate(node, Facts({}, {"demographics.age_years": 17})) is True
    assert evaluate(node, Facts({}, {"demographics.age_years": 18})) is False


@pytest.mark.parametrize(
    "bad",
    [
        {"op": "exec", "code": "import os"},
        {"op": "present", "feature": "zzz"},
        {"op": "present", "feature": "a", "extra": 1},
        {"op": "and", "args": []},
        {"op": "compare", "field": "session.owner", "cmp": "eq", "value": 1},
        {"op": "compare", "field": "demographics.age_years", "cmp": "eq", "value": True},
        "present(a)",
    ],
)
def test_validator_rejects_anything_outside_the_bounded_grammar(bad):
    with pytest.raises(RuleValidationError):
        validate_ast(bad, F)


def test_validator_bounds_depth():
    node = present_a
    for _ in range(9):
        node = {"op": "not", "arg": node}
    with pytest.raises(RuleValidationError, match="depth"):
        validate_ast(node, F)
