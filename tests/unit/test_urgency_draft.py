"""The draft urgency rule set (M2.10): it is whole, every rule is founded and tested, and it cannot be served.

The draft file is real content awaiting review. These tests check its form and that it stays a draft; they do
not judge whether a rule is medically right."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from feeltriva_clinical import BundleError, Facts, evaluate, load_bundle, load_fixture_bundle, validate_bundle
from feeltriva_clinical.bundle import EvidenceItem, Feature, ReleaseBundle
from feeltriva_clinical.urgency_draft import (
    DRAFT_PATH,
    DraftError,
    UrgencyDraft,
    check_draft,
    load_draft,
    review_document,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def _changed(change) -> UrgencyDraft:
    """The draft with one change made to its plain form, checked for its shape only."""
    plain = load_draft().model_dump()
    change(plain)
    return UrgencyDraft.model_validate(plain)


def test_the_draft_is_whole_pending_and_every_rule_has_a_basis_and_a_reason():
    draft = load_draft()
    assert draft.status == "pending" and "Unreviewed draft" in draft.label and "not by a clinician" in draft.label
    assert len(draft.rules) == 20 and {rule.status for rule in draft.rules} == {"pending"}
    levels = [rule.action.urgency for rule in sorted(draft.rules, key=lambda rule: rule.priority)]
    assert levels == ["emergency"] * 12 + ["urgent"] * 8  # every emergency rule is checked before every urgent one
    sources = {source.evidence_id: source for source in draft.sources}
    for rule in draft.rules:
        assert rule.rule_type == "urgency" and rule.action.type == "escalate" and rule.why_this_level
        assert any(evidence.startswith("nhs.") for evidence in rule.evidence_ids), rule.rule_id
        assert all(
            sources[evidence].quotes and sources[evidence].source_url.startswith("https://")
            for evidence in rule.evidence_ids
        )
    assert draft.open_points and draft.not_covered  # what is not settled and not covered is said in the draft itself


def test_every_rule_fires_on_its_case_stays_silent_on_its_other_case_and_never_fires_on_nothing():
    draft = load_draft()
    for rule in draft.rules:
        fired = []
        for case in rule.tests:
            presence = {**dict.fromkeys(case.absent, "absent"), **dict.fromkeys(case.present, "present")}
            fired.append(evaluate(rule.condition_ast, Facts(presence=presence)) is True)
            assert fired[-1] == case.fires, rule.rule_id
        assert sorted(fired) == [False, True], rule.rule_id
        # Nothing known, and everything merely not asked: no rule fires. Unknown is never taken for present.
        assert evaluate(rule.condition_ast, Facts()) is not True
        unasked = dict.fromkeys((feature.feature_id for feature in draft.features), "not_asked")
        assert evaluate(rule.condition_ast, Facts(presence=unasked)) is not True


def test_the_texts_shown_name_only_numbers_that_have_a_basis():
    draft = load_draft()
    for rule in draft.rules:
        numbers = set(re.findall(r"\b\d{3,}\b", rule.action.text))
        assert numbers <= {"112", "14416"}, rule.rule_id
        if "112" in numbers:
            assert "india.112" in rule.evidence_ids, rule.rule_id
        if "14416" in numbers:
            assert "india.telemanas" in rule.evidence_ids, rule.rule_id
        assert "diagnos" not in rule.action.text.lower() or "not a diagnosis" in rule.action.text.lower()
    quoted = " ".join(quote for source in draft.sources for quote in source.quotes)
    assert "112" in quoted and "14416" in quoted


def test_a_draft_cannot_approve_itself():
    with pytest.raises(ValidationError):
        _changed(lambda plain: plain.update(status="approved"))
    with pytest.raises(ValidationError):
        _changed(lambda plain: plain["rules"][0].update(status="approved"))


def test_the_draft_cannot_be_served():
    # It is not a release bundle, so it cannot be loaded as one ...
    with pytest.raises(ValidationError):
        load_bundle(DRAFT_PATH, clinical_mode=False)
    # ... and a bundle built from it is refused in clinical mode: nothing in it is approved.
    draft, fixture = load_draft(), load_fixture_bundle()
    bundle = ReleaseBundle(
        bundle_id=draft.draft_id,
        rules_version=draft.version,
        knowledge_release_id="none",
        knowledge_version="none",
        synthetic=False,
        status=draft.status,
        features=[Feature(feature_id=feature.feature_id, preferred_name=feature.name) for feature in draft.features],
        rules=draft.as_rules(),
        questions=[],
        candidates=[],
        evidence=[
            EvidenceItem(
                evidence_id=source.evidence_id,
                source_title=source.source_title,
                source_url=source.source_url,
                excerpt=" ".join(source.quotes),
            )
            for source in draft.sources
        ],
        templates=fixture.templates,
    )
    validate_bundle(bundle, clinical_mode=False)  # well formed
    with pytest.raises(BundleError, match="not approved"):
        validate_bundle(bundle, clinical_mode=True)
    # What the service loads by default is the synthetic fixture, which holds no rule of the draft.
    assert not {rule.rule_id for rule in fixture.rules} & {rule.rule_id for rule in draft.rules}
    assert fixture.synthetic and all(not rule.rule_id.startswith("urg.") for rule in fixture.rules)


def test_a_draft_that_is_not_whole_is_refused_and_says_why():
    def unknown_feature(plain):
        plain["rules"][0]["condition_ast"] = {"op": "present", "feature": "feat_not_in_the_draft"}

    def wrong_test(plain):
        plain["rules"][0]["tests"][0]["fires"] = False

    def unknown_basis(plain):
        plain["rules"][0]["evidence_ids"] = ["nhs.no_such_page"]

    def urgent_before_emergency(plain):
        plain["rules"][0]["priority"] = 500

    def no_reason(plain):
        plain["rules"][0]["why_this_level"] = " "

    for change, message in (
        (unknown_feature, "unknown feature"),
        (wrong_test, "a case that fires"),
        (unknown_basis, "unknown basis"),
        (urgent_before_emergency, "every emergency rule must come before"),
        (no_reason, "no reason for its level"),
    ):
        with pytest.raises(DraftError, match=message):
            check_draft(_changed(change))


def test_the_review_document_is_generated_from_the_draft_and_is_current():
    draft = load_draft()
    document = review_document(draft)
    assert (ROOT / "docs" / "review" / "urgency_rules_draft.md").read_text(encoding="utf-8") == document
    assert draft.label in document and all(
        rule.rule_id in document and rule.action.text in document for rule in draft.rules
    )
    assert all(point in document for point in draft.open_points)
