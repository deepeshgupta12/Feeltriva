"""Release bundle: features, rules, questions, candidates and evidence used for serving.

A bundle is loaded and fully validated before use. Clinical mode only accepts a
non-synthetic bundle whose status and every served item are 'approved'. The shipped
fixture bundle is synthetic, nonmedical and can never be served in clinical mode.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .answers import AnswerValidationError, validate_answer_schema
from .rules import Facts, RuleValidationError, evaluate, validate_ast

ReviewState = Literal["pending", "approved", "rejected", "retired"]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fixture_release.json"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Feature(_Strict):
    feature_id: str
    preferred_name: str
    kind: Literal["symptom", "sign", "history", "risk_factor", "measurement", "other"] = "other"
    value_type: Literal["boolean", "number", "category", "text"] = "boolean"
    aliases: list[str] = []
    status: ReviewState = "pending"


class RuleAction(_Strict):
    type: Literal["escalate", "clarify", "exclude_from_scope", "continue"]
    text: str
    urgency: Literal["emergency", "urgent"] | None = None


class Rule(_Strict):
    rule_id: str
    rule_type: Literal["urgency", "scope"]
    condition_ast: dict[str, Any]
    action: RuleAction
    evidence_ids: list[str] = []
    priority: int
    status: ReviewState = "pending"


class Question(_Strict):
    question_id: str
    feature_id: str
    wording: str
    answer_schema: dict[str, Any]
    option_presence: dict[str, str] = {}
    applicability: dict[str, Any] | None = None
    evidence_ids: list[str] = []
    priority: int = 100
    # The reviewer's mark that the assessment needs this answer whatever else is known (M3.8): such a question is
    # asked before the ones that only tell possible explanations apart.
    essential: bool = False
    status: ReviewState = "pending"


class CandidateDef(_Strict):
    disease_id: str
    name: str
    explanation: str
    condition_ast: dict[str, Any]
    evidence_ids: list[str] = Field(min_length=1)
    status: ReviewState = "pending"


class EvidenceItem(_Strict):
    evidence_id: str
    source_title: str
    source_url: str | None = None
    excerpt: str
    status: ReviewState = "pending"


class Templates(_Strict):
    """Reviewer-authored response texts. The service never composes care guidance itself."""

    provisional_next_step: str
    insufficient_information: str
    confirm_details: str
    system_unavailable: str


class ReleaseBundle(_Strict):
    bundle_id: str
    rules_version: str
    # Both None when the bundle carries no knowledge release: it then has no candidates and no evidence.
    knowledge_release_id: str | None
    knowledge_version: str | None
    synthetic: bool
    status: ReviewState
    features: list[Feature]
    rules: list[Rule]
    questions: list[Question]
    candidates: list[CandidateDef]
    evidence: list[EvidenceItem]
    templates: Templates

    def feature_ids(self) -> set[str]:
        return {f.feature_id for f in self.features}

    def question(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.question_id == question_id), None)

    def feature(self, feature_id: str) -> Feature | None:
        return next((f for f in self.features if f.feature_id == feature_id), None)


class BundleError(ValueError):
    pass


def validate_bundle(bundle: ReleaseBundle, *, clinical_mode: bool) -> None:
    features = bundle.feature_ids()
    if len(features) != len(bundle.features):
        raise BundleError("duplicate feature_id")
    for label, ids in (
        ("rule", [r.rule_id for r in bundle.rules]),
        ("question", [q.question_id for q in bundle.questions]),
        ("candidate", [c.disease_id for c in bundle.candidates]),
        ("evidence", [e.evidence_id for e in bundle.evidence]),
    ):
        if len(set(ids)) != len(ids):
            raise BundleError(f"duplicate {label} id")
    try:
        for rule in bundle.rules:
            validate_ast(rule.condition_ast, features)
            if rule.rule_type == "urgency" and rule.action.type == "escalate" and not rule.action.urgency:
                raise BundleError(f"escalation rule {rule.rule_id} needs an urgency level")
        for q in bundle.questions:
            if q.feature_id not in features:
                raise BundleError(f"question {q.question_id} references unknown feature")
            validate_answer_schema(q.answer_schema)
            if q.applicability is not None:
                validate_ast(q.applicability, features)
        for c in bundle.candidates:
            validate_ast(c.condition_ast, features)
    except (RuleValidationError, AnswerValidationError) as exc:
        raise BundleError(str(exc)) from exc
    named = given_by_its_own_name(bundle)
    if named:
        candidate, feature = named[0]
        raise BundleError(
            f'"{candidate.name}" would be given from "{feature.preferred_name}" alone. A complaint that is also the '
            "everyday name of a condition leads to follow-up questions, never to that condition by itself "
            f"(decision E65); {len(named)} such pairs in this bundle"
        )
    if (bundle.knowledge_release_id is None) != (bundle.knowledge_version is None):
        raise BundleError("a knowledge release is named by its ID and its version, or not at all")
    if bundle.knowledge_version is None and (bundle.candidates or bundle.evidence):
        raise BundleError("candidates and evidence need a knowledge release")
    if clinical_mode:
        if bundle.synthetic:
            raise BundleError("synthetic fixture bundle cannot be served in clinical mode")
        if bundle.status != "approved":
            raise BundleError("bundle is not approved")
        pending = [
            item
            for group in (bundle.features, bundle.rules, bundle.questions, bundle.candidates, bundle.evidence)
            for item in group
            if item.status != "approved"
        ]
        if pending:
            raise BundleError(f"{len(pending)} bundle items are not approved")


def _words(name: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).split()


def given_by_its_own_name(bundle: ReleaseBundle) -> list[tuple[CandidateDef, Feature]]:
    """The possible explanations that one reported detail would give by itself, where that detail carries the
    explanation's own name or a word sequence of it ("cold" and "common cold"). Owner's rule E65: the word a
    person uses for a complaint is not the condition; the conditions it could be are told apart by questions."""
    found = []
    for candidate in bundle.candidates:
        name = _words(candidate.name)
        for feature in bundle.features:
            words = _words(feature.preferred_name)
            inside = words and any(name[i : i + len(words)] == words for i in range(len(name) - len(words) + 1))
            if inside and evaluate(candidate.condition_ast, Facts({feature.feature_id: "present"})) is True:
                found.append((candidate, feature))
    return found


def load_bundle(path: Path, *, clinical_mode: bool) -> ReleaseBundle:
    bundle = ReleaseBundle.model_validate(json.loads(path.read_text(encoding="utf-8")))
    validate_bundle(bundle, clinical_mode=clinical_mode)
    return bundle


def load_fixture_bundle() -> ReleaseBundle:
    return load_bundle(FIXTURE_PATH, clinical_mode=False)
