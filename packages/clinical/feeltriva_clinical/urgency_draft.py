"""The draft urgency rule set (M2.10): reading it, checking it and writing it out for review.

Owner decision E39: the urgency and escalation rules are drafted by the engineering assistant,
not by a clinician. The draft is a file, `drafts/urgency_draft.json`. Every rule in it

- is written in the rule format of `rules.py` against features of the real vocabulary;
- names the published warning sign it rests on, quoted word for word with its source;
- says why it has the urgency level it has;
- carries a case that makes it fire and a case that does not.

The draft is written out as two documents by `urgency_documents.py`.

A draft is not a release. Its status and the status of every rule can only be `pending`: the
file cannot approve itself. It has no questions, candidates or templates, so it cannot be loaded
as a release bundle, and a bundle built from it is refused in clinical mode because nothing in it
is approved. Nothing here is medical advice that anyone is shown.

This module is pure: it reads one file and no database.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .bundle import Rule, RuleAction
from .rules import Facts, RuleValidationError, evaluate, referenced_features, validate_ast

DRAFT_PATH = Path(__file__).parent / "drafts" / "urgency_draft.json"


_NUMBER = re.compile(r"\b\d{3,}\b")  # anything in a text shown that could be dialled


class DraftError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DraftSource(_Strict):
    evidence_id: str
    publisher: str
    source_title: str
    source_url: str
    page_reviewed: str  # the page's own "last reviewed" date; empty when the page gives none
    licence: str
    quotes: list[str] = Field(min_length=1)  # word for word from the page


class DraftFeature(_Strict):
    feature_id: str
    name: str  # the feature's name in the vocabulary
    question: str | None = None  # the source's full question, where the feature is a question


class DraftTest(_Strict):
    present: list[str]
    absent: list[str] = []
    fires: bool


class DraftRule(_Strict):
    rule_id: str
    rule_type: Literal["urgency"]
    title: str
    condition_ast: dict[str, Any]
    action: RuleAction
    evidence_ids: list[str] = Field(min_length=1)
    priority: int
    status: Literal["pending"]
    why_this_level: str
    tests: list[DraftTest]


class NotCovered(_Strict):
    sign: str
    why: str


class DraftNumber(_Strict):
    """A telephone number that a text shown to a person may name."""

    number: str
    what: str
    evidence_ids: list[str] = Field(min_length=1)
    confirmed_by_owner: str = ""  # the date the owner confirmed the number; empty until then


class DraftChange(_Strict):
    date: str
    change: str


class UrgencyDraft(_Strict):
    draft_id: str
    version: str
    status: Literal["pending"]
    label: str
    jurisdiction: str
    written: str
    history: list[DraftChange]
    numbers: list[DraftNumber]
    sources: list[DraftSource]
    features: list[DraftFeature]
    rules: list[DraftRule]
    not_covered: list[NotCovered]
    open_points: list[str]  # what the owner has to decide or confirm before approval
    limits: list[str]  # weaknesses that remain whatever is decided

    def as_rules(self) -> list[Rule]:
        """The rules in the form a release bundle holds them."""
        return [
            Rule(
                rule_id=rule.rule_id,
                rule_type=rule.rule_type,
                condition_ast=rule.condition_ast,
                action=rule.action,
                evidence_ids=rule.evidence_ids,
                priority=rule.priority,
                status=rule.status,
            )
            for rule in self.rules
        ]


def check_draft(draft: UrgencyDraft) -> None:
    """Raise DraftError unless the draft is whole: every rule valid, founded and tested."""
    features = {feature.feature_id for feature in draft.features}
    sources = {source.evidence_id for source in draft.sources}
    for label, ids, count in (
        ("feature", features, len(draft.features)),
        ("source", sources, len(draft.sources)),
        ("rule", {rule.rule_id for rule in draft.rules}, len(draft.rules)),
        ("priority", {rule.priority for rule in draft.rules}, len(draft.rules)),
    ):
        if len(ids) != count:
            raise DraftError(f"duplicate {label}")
    used: set[str] = set()
    for rule in draft.rules:
        try:
            validate_ast(rule.condition_ast, features)
        except RuleValidationError as error:
            raise DraftError(f"{rule.rule_id}: {error}") from error
        used.update(referenced_features(rule.condition_ast))
        if rule.action.type != "escalate" or rule.action.urgency is None or not rule.action.text.strip():
            raise DraftError(f"{rule.rule_id}: an urgency rule escalates, with a level and a text")
        unknown = sorted(set(rule.evidence_ids) - sources)
        if unknown:
            raise DraftError(f"{rule.rule_id}: unknown basis {unknown}")
        if not rule.why_this_level.strip():
            raise DraftError(f"{rule.rule_id}: no reason for its level")
        if {test.fires for test in rule.tests} != {True, False}:
            raise DraftError(f"{rule.rule_id}: needs a case that fires and a case that does not")
        for test in rule.tests:
            named = set(test.present) | set(test.absent)
            if not named <= features:
                raise DraftError(f"{rule.rule_id}: a test names an unknown feature")
            presence = {**dict.fromkeys(test.absent, "absent"), **dict.fromkeys(test.present, "present")}
            fired = evaluate(rule.condition_ast, Facts(presence=presence)) is True
            if fired != test.fires:
                raise DraftError(f"{rule.rule_id}: a test expects fires={test.fires} and the rule gives {fired}")
    if used != features:
        raise DraftError(f"{len(features - used)} listed features are used by no rule")
    numbers = {entry.number: set(entry.evidence_ids) for entry in draft.numbers}
    if len(numbers) != len(draft.numbers) or not all(ids <= sources for ids in numbers.values()):
        raise DraftError("the telephone numbers are listed twice or rest on an unknown basis")
    dialled: set[str] = set()
    for rule in draft.rules:
        for number in set(_NUMBER.findall(rule.action.text)):
            if number not in numbers:
                raise DraftError(f"{rule.rule_id}: its text names the number {number}, which the draft does not list")
            if not numbers[number] & set(rule.evidence_ids):
                raise DraftError(f"{rule.rule_id}: its text names {number} without that number's basis")
            dialled.add(number)
    if dialled != set(numbers):
        raise DraftError("a listed telephone number is named in no text")
    emergency = [rule.priority for rule in draft.rules if rule.action.urgency == "emergency"]
    urgent = [rule.priority for rule in draft.rules if rule.action.urgency == "urgent"]
    if emergency and urgent and max(emergency) >= min(urgent):
        raise DraftError("every emergency rule must come before every urgent rule")


def load_draft(path: Path = DRAFT_PATH) -> UrgencyDraft:
    draft = UrgencyDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))
    check_draft(draft)
    return draft


def draft_digest(path: Path = DRAFT_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
