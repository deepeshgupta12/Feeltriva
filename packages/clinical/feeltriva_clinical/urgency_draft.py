"""The draft urgency rule set (M2.10): reading it, checking it and writing it out for review.

Owner decision E39: the urgency and escalation rules are drafted by the engineering assistant,
not by a clinician. The draft is a file, `drafts/urgency_draft.json`. Every rule in it

- is written in the rule format of `rules.py` against features of the real vocabulary;
- names the published warning sign it rests on, quoted word for word with its source;
- says why it has the urgency level it has;
- carries a case that makes it fire and a case that does not.

A draft is not a release. Its status and the status of every rule can only be `pending`: the
file cannot approve itself. It has no questions, candidates or templates, so it cannot be loaded
as a release bundle, and a bundle built from it is refused in clinical mode because nothing in it
is approved. Nothing here is medical advice that anyone is shown.

This module is pure: it reads one file and no database.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .bundle import Rule, RuleAction
from .rules import Facts, RuleValidationError, evaluate, referenced_features, validate_ast

DRAFT_PATH = Path(__file__).parent / "drafts" / "urgency_draft.json"


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


class UrgencyDraft(_Strict):
    draft_id: str
    version: str
    status: Literal["pending"]
    label: str
    jurisdiction: str
    written: str
    sources: list[DraftSource]
    features: list[DraftFeature]
    rules: list[DraftRule]
    not_covered: list[NotCovered]
    open_points: list[str]

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


def _condition(node: dict[str, Any], names: dict[str, str]) -> str:
    """A condition in words, for a reader who does not read the rule format."""
    op = node["op"]
    if op == "present":
        return f"“{names[node['feature']]}”"
    parts = [_condition(child, names) for child in node["args"]]
    if op == "or":
        return (
            "any of: " + "; ".join(parts)
            if all(c["op"] == "present" for c in node["args"])
            else " OR ".join(f"({part})" for part in parts)
        )
    return " AND ".join(f"({part})" for part in parts)


def review_document(draft: UrgencyDraft) -> str:
    """The draft as a document for the owner's review. Generated: edit the draft file, not this text."""
    names = {feature.feature_id: feature.question or feature.name for feature in draft.features}
    sources = {source.evidence_id: source for source in draft.sources}
    lines = [
        "# Urgency rules: draft for the owner's review",
        "",
        f"**{draft.label}**",
        "",
        f"Version `{draft.version}`, written {draft.written}, for {draft.jurisdiction}. Status: `{draft.status}`. "
        "This document is generated from `packages/clinical/feeltriva_clinical/drafts/urgency_draft.json`; "
        "change the file, not this text.",
        "",
        "## How to read it",
        "",
        "- A rule fires only when the answers given so far make its condition true. A symptom nobody has asked "
        "about counts as unknown, never as absent.",
        "- **Emergency** rules are checked before **urgent** ones, and the first rule that fires decides the text shown.",
        "- The words in quotation marks are features of the vocabulary; a question is shown where the feature is one.",
        "- Each basis is quoted word for word from the page named, with the date the page says it was last reviewed.",
        "",
        "## Open points for the owner",
        "",
        *[f"{number}. {point}" for number, point in enumerate(draft.open_points, 1)],
        "",
        "## Warning signs the draft does not cover",
        "",
        "| Published warning sign | Why there is no rule |",
        "|---|---|",
        *[f"| {item.sign} | {item.why} |" for item in draft.not_covered],
        "",
        "## The rules",
    ]
    for number, rule in enumerate(sorted(draft.rules, key=lambda item: item.priority), 1):
        lines += [
            "",
            f"### {number}. {rule.title}",
            "",
            f"- **Rule:** `{rule.rule_id}`, level **{rule.action.urgency}**, priority {rule.priority}, status `{rule.status}`",
            f"- **Fires when:** {_condition(rule.condition_ast, names)}",
            f"- **Text shown:** {rule.action.text}",
            f"- **Why this level:** {rule.why_this_level}",
            "- **Basis:**",
        ]
        for evidence_id in rule.evidence_ids:
            source = sources[evidence_id]
            reviewed = f", page last reviewed {source.page_reviewed}" if source.page_reviewed else ""
            lines.append(f"  - {source.publisher}, [{source.source_title}]({source.source_url}){reviewed}:")
            lines += [f"    - “{quote}”" for quote in source.quotes]
    lines += [
        "",
        "## Sources and licences",
        "",
        "| Source | Licence and attribution |",
        "|---|---|",
        *[
            f"| {source.publisher}: [{source.source_title}]({source.source_url}) | {source.licence} |"
            for source in draft.sources
        ],
        "",
        "Information from the NHS website is licensed under the "
        "[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). "
        "The rules and the texts shown are this project's own wording and are not NHS content.",
        "",
    ]
    return "\n".join(lines)
