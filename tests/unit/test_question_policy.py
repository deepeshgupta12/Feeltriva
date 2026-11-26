"""How the next follow-up question is chosen (M3.8), on invented bundles. Nothing here is medical content."""

from __future__ import annotations

from typing import Any

import pytest
from feeltriva_clinical import BundleError, Facts, question_order, validate_bundle
from feeltriva_clinical.bundle import ReleaseBundle
from feeltriva_clinical.engine import ESSENTIAL, INFORMATIVE, OTHER, SAFETY, next_question
from feeltriva_clinical.rules import evaluate

YES_NO = {"type": "yes_no_unsure"}
TEXTS = {
    "provisional_next_step": "Sample text.",
    "insufficient_information": "Sample text.",
    "confirm_details": "Sample text.",
    "system_unavailable": "Sample text.",
}


def present(feature: str) -> dict[str, Any]:
    return {"op": "present", "feature": feature}


def both(*args: dict[str, Any]) -> dict[str, Any]:
    return {"op": "and", "args": list(args)}


def bundle(features, questions, candidates=(), rules=()) -> ReleaseBundle:
    """An invented bundle. A question is (id, feature, more fields); a candidate is (name, condition)."""
    made = ReleaseBundle(
        bundle_id="invented",
        rules_version="invented-0",
        knowledge_release_id="invented-knowledge" if candidates else None,
        knowledge_version="0" if candidates else None,
        synthetic=True,
        status="pending",
        features=[
            {"feature_id": f, "preferred_name": name, "kind": "symptom", "value_type": "boolean"}
            for f, name in features.items()
        ],
        rules=[
            {
                "rule_id": rule_id,
                "rule_type": "urgency",
                "condition_ast": condition,
                "action": {"type": "escalate", "urgency": "urgent", "text": "Sample text (invented)."},
                "priority": priority,
            }
            for rule_id, condition, priority in rules
        ],
        questions=[
            {
                "question_id": qid,
                "feature_id": feature,
                "wording": f"Invented question {qid}?",
                **{"answer_schema": YES_NO, **more},
            }
            for qid, feature, more in questions
        ],
        candidates=[
            {
                "disease_id": f"c.{n}",
                "name": name,
                "explanation": "Invented.",
                "condition_ast": condition,
                "evidence_ids": ["e1"],
            }
            for n, (name, condition) in enumerate(candidates)
        ],
        evidence=[{"evidence_id": "e1", "source_title": "Invented source", "excerpt": "Invented."}]
        if candidates
        else [],
        templates=TEXTS,
    )
    validate_bundle(made, clinical_mode=False)
    return made


def asked(order) -> list[str]:
    return [ranked.question.question_id for ranked in order]


def test_a_safety_question_comes_before_every_other_and_is_not_asked_twice():
    features = {
        "danger": "pretend danger sign",
        "later": "pretend later sign",
        "tells": "pretend telling sign",
        "x": "pretend x",
    }
    made = bundle(
        features,
        questions=[
            # The reviewer's own order puts the safety question last and makes it the hardest to answer.
            ("q.tells", "tells", {"priority": 1}),
            ("q.later", "later", {"priority": 2}),
            ("q.danger", "danger", {"priority": 99, "answer_schema": {"type": "free_text"}}),
        ],
        candidates=[("pretend illness", both(present("x"), present("tells")))],
        rules=[("r.late", present("later"), 50), ("r.first", present("danger"), 10)],
    )
    order = question_order(made, Facts({"x": "present"}))
    # The answer that could decide the earlier urgency rule first, then the other rule's, then the telling one.
    assert asked(order) == ["q.danger", "q.later", "q.tells"]
    assert [ranked.reason for ranked in order] == [SAFETY, SAFETY, INFORMATIVE]
    assert (order[0].open_rule_priority, order[2].open_candidates) == (10, 1)
    # Whatever was answered, a question is not asked again; the next one moves up.
    for answer in ("absent", "uncertain", "present"):
        again = question_order(made, Facts({"x": "present", "danger": answer}))
        assert "q.danger" not in asked(again) and asked(again)[0] == "q.later"
    assert (
        next_question(made, Facts({"x": "present", "danger": "absent", "later": "absent", "tells": "absent"})) is None
    )


def test_essentials_then_what_tells_most_apart_then_the_easier_answer_then_the_reviewers_order():
    features = {name: f"pretend {name}" for name in ("x", "must", "two", "one", "easy", "plain", "last")}
    made = bundle(
        features,
        questions=[
            ("q.last", "last", {"priority": 1}),
            ("q.plain", "plain", {"priority": 5}),
            ("q.one", "one", {"priority": 2, "answer_schema": {"type": "free_text"}}),
            ("q.easy", "easy", {"priority": 9}),
            ("q.two", "two", {"priority": 3, "answer_schema": {"type": "number"}}),
            ("q.must", "must", {"priority": 50, "essential": True, "answer_schema": {"type": "duration"}}),
        ],
        candidates=[
            ("pretend illness a", both(present("x"), present("two"), present("one"))),
            ("pretend illness b", both(present("x"), present("two"), present("easy"))),
        ],
    )
    order = question_order(made, Facts({"x": "present"}))
    assert asked(order) == ["q.must", "q.two", "q.easy", "q.one", "q.last", "q.plain"]
    assert [ranked.reason for ranked in order] == [ESSENTIAL, INFORMATIVE, INFORMATIVE, INFORMATIVE, OTHER, OTHER]
    # "two" bears on both undecided explanations; "easy" and "one" on one each, and a yes or no is the easier.
    assert [ranked.open_candidates for ranked in order[1:4]] == [2, 1, 1]
    # A decided explanation no longer makes a question informative.
    decided = question_order(made, Facts({"x": "present", "two": "absent"}))
    assert asked(decided) == ["q.must", "q.last", "q.plain", "q.easy", "q.one"]
    # A question that does not apply yet is not offered.
    gated = bundle({"x": "pretend x", "y": "pretend y"}, questions=[("q.y", "y", {"applicability": present("x")})])
    assert asked(question_order(gated, Facts({}))) == [] and asked(question_order(gated, Facts({"x": "present"}))) == [
        "q.y"
    ]


def test_the_same_explanations_are_decided_with_fewer_questions_than_in_the_fixed_order():
    features = {name: f"pretend {name}" for name in ("x", "a", "b", "idle1", "idle2", "idle3")}
    made = bundle(
        features,
        questions=[
            ("q.idle1", "idle1", {"priority": 1}),
            ("q.idle2", "idle2", {"priority": 2}),
            ("q.a", "a", {"priority": 3}),
            ("q.idle3", "idle3", {"priority": 4}),
            ("q.b", "b", {"priority": 5}),
        ],
        candidates=[
            ("pretend illness a", both(present("x"), present("a"))),
            ("pretend illness b", both(present("x"), present("b"))),
        ],
    )

    def needed(pick) -> int:
        """Questions asked, everything answered "no", until no possible explanation is undecided."""
        known = {"x": "present"}
        for count in range(10):
            if all(evaluate(c.condition_ast, Facts(known)) is not None for c in made.candidates):
                return count
            known[pick(Facts(known)).feature_id] = "absent"
        raise AssertionError("never decided")

    def fixed(facts):  # the order used before M3.8: the reviewer's priority alone
        open_ = [q for q in sorted(made.questions, key=lambda q: q.priority) if q.feature_id not in facts.presence]
        return open_[0]

    assert (needed(lambda facts: next_question(made, facts)), needed(fixed)) == (2, 5)


def test_a_complaint_that_is_also_the_name_of_a_condition_leads_to_questions_not_to_that_condition():
    # The owner's rule E65, with the owner's own example. The conditions and what tells them apart are invented
    # for the test: no medical content is taken from here.
    features = {"cold": "cold", "nose": "pretend runny nose", "fever": "pretend fever"}
    questions = [("q.fever", "fever", {}), ("q.nose", "nose", {})]
    made = bundle(
        features,
        questions,
        candidates=[
            ("common cold", both(present("cold"), present("nose"), {"op": "absent", "feature": "fever"})),
            ("pretend other illness", both(present("cold"), present("fever"))),
        ],
    )
    only_cold = Facts({"cold": "present"})
    # Nothing is given from the word alone, and a question that tells the possibilities apart is asked.
    assert [evaluate(c.condition_ast, only_cold) for c in made.candidates] == [None, None]
    first = question_order(made, only_cold)[0]
    assert (first.question.question_id, first.reason, first.open_candidates) == ("q.fever", INFORMATIVE, 2)
    # A bundle in which the word alone would give the condition does not load.
    with pytest.raises(BundleError, match="E65"):
        bundle(features, questions, candidates=[("common cold", present("cold"))])
    with pytest.raises(BundleError, match='"pretend fever of the test" would be given from "pretend fever" alone'):
        bundle(
            features,
            questions,
            candidates=[("pretend fever of the test", {"op": "or", "args": [present("fever"), present("nose")]})],
        )
    # Another condition may rest on that one detail: the rule is about a condition's own name.
    bundle(features, questions, candidates=[("pretend other illness", present("cold"))])
