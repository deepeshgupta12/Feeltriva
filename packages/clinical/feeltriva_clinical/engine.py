"""Deterministic screening and question selection over a validated bundle."""

from __future__ import annotations

from dataclasses import dataclass

from .bundle import Question, ReleaseBundle, Rule
from .rules import Facts, evaluate


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


def next_question(bundle: ReleaseBundle, facts: Facts) -> Question | None:
    """First applicable question whose feature has never been observed. One at a time; no repeats."""
    for q in sorted(bundle.questions, key=lambda q: q.priority):
        if facts.presence.get(q.feature_id) not in (None, "not_asked"):
            continue
        if q.applicability is not None and evaluate(q.applicability, facts) is not True:
            continue
        return q
    return None
