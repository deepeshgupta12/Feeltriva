"""Deterministic screening and question selection over a validated bundle."""

from __future__ import annotations

from dataclasses import dataclass

from .bundle import Question, ReleaseBundle, Rule
from .rules import Facts, evaluate, referenced_features


@dataclass(frozen=True)
class Screening:
    escalation: Rule | None
    scope_exclusion: Rule | None


def screen(bundle: ReleaseBundle, facts: Facts) -> Screening:
    """Urgency and scope rules. Runs on every observation change, before any ranking."""
    escalation = scope = None
    for rule in sorted(bundle.rules, key=lambda r: r.priority):
        if evaluate(rule.condition_ast, facts) is not True:
            continue
        if rule.action.type == "escalate" and escalation is None:
            escalation = rule
        elif rule.action.type == "exclude_from_scope" and scope is None:
            scope = rule
    return Screening(escalation, scope)


# How much an answer asks of the person, by the kind of answer: a tap, a choice, something to work out, writing.
BURDEN = {
    "yes_no_unsure": 1,
    "single_choice": 2,
    "multiple_choice": 3,
    "number": 3,
    "duration": 3,
    "date": 3,
    "free_text": 4,
}
SAFETY, ESSENTIAL, INFORMATIVE, OTHER = "safety", "essential", "informative", "other"


@dataclass(frozen=True)
class RankedQuestion:
    """A question that can be asked now, with why it stands where it does in the order."""

    question: Question
    reason: str
    # The earliest urgency or scope rule, by its priority, that this answer could decide; None when there is none.
    open_rule_priority: int | None
    # How many possible explanations that are not decided yet depend on this answer.
    open_candidates: int
    burden: int


def question_order(bundle: ReleaseBundle, facts: Facts) -> list[RankedQuestion]:
    """The questions that can be asked now, in the order they are asked (M3.8).

    1. Safety: the answer could decide an urgency or scope rule that is not decided yet. The earlier rule first.
    2. Missing essentials: the reviewer marked the question as needed whatever else is known.
    3. Information value: the answer bears on possible explanations that are not decided yet; more of them first.
       This is counted from the reviewed conditions of the bundle only, never from data counts.
    4. Burden: the easier kind of answer first.
    Then the reviewer's own order, then the question's ID, so that the order is always the same.

    A question is never repeated: one whose detail has been observed is not in the list. None is left out either:
    the policy orders, it does not end the questioning.
    """
    open_rules = [
        (rule.priority, set(referenced_features(rule.condition_ast)))
        for rule in bundle.rules
        if evaluate(rule.condition_ast, facts) is None
    ]
    open_candidates = [
        set(referenced_features(candidate.condition_ast))
        for candidate in bundle.candidates
        if evaluate(candidate.condition_ast, facts) is None
    ]
    ranked = []
    for q in bundle.questions:
        if facts.presence.get(q.feature_id) not in (None, "not_asked"):
            continue
        if q.applicability is not None and evaluate(q.applicability, facts) is not True:
            continue
        deciding = [priority for priority, named in open_rules if q.feature_id in named]
        bearing = sum(1 for named in open_candidates if q.feature_id in named)
        reason = SAFETY if deciding else ESSENTIAL if q.essential else INFORMATIVE if bearing else OTHER
        ranked.append(
            RankedQuestion(
                question=q,
                reason=reason,
                open_rule_priority=min(deciding) if deciding else None,
                open_candidates=bearing,
                burden=BURDEN.get(str(q.answer_schema.get("type")), max(BURDEN.values())),
            )
        )
    tier = {SAFETY: 0, ESSENTIAL: 1, INFORMATIVE: 2, OTHER: 3}
    return sorted(
        ranked,
        key=lambda r: (
            tier[r.reason],
            r.open_rule_priority if r.reason == SAFETY else 0,
            -r.open_candidates if r.reason == INFORMATIVE else 0,
            r.burden,
            r.question.priority,
            r.question.question_id,
        ),
    )


def next_question(bundle: ReleaseBundle, facts: Facts) -> Question | None:
    """The question to ask now, by the policy of `question_order`. One at a time; no repeats."""
    order = question_order(bundle, facts)
    return order[0].question if order else None
