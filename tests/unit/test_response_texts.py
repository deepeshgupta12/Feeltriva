"""The draft response texts of a release (M2.5f1): the four texts, in order, pending, and never self-approved."""

from __future__ import annotations

from pathlib import Path

import pytest
from feeltriva_clinical.bundle import Templates
from feeltriva_clinical.response_texts import (
    REVIEW_FILE,
    ResponseTextError,
    ResponseTexts,
    check_texts,
    load_response_texts,
    review_document,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def _changed(change) -> ResponseTexts:
    plain = load_response_texts().model_dump()
    change(plain)
    return ResponseTexts.model_validate(plain)


def test_the_draft_holds_exactly_the_four_texts_of_a_release_and_is_pending():
    draft = load_response_texts()
    assert draft.status == "pending" and "Not approved" in draft.label and "not by a clinician" in draft.label
    assert sorted(entry.key for entry in draft.texts) == sorted(Templates.model_fields)
    templates = draft.as_templates()
    assert templates.confirm_details.startswith("Before we continue")
    for entry in draft.texts:
        assert entry.shown_when and entry.why
        lowered = entry.text.lower()
        assert "%" not in entry.text and ("diagnos" not in lowered or "not a diagnosis" in lowered)
    # Finding nothing, and failing, must not read as reassurance or as a result.
    assert "This does not mean that nothing is wrong." in templates.insufficient_information
    assert "Nothing has been concluded about your symptoms." in templates.system_unavailable
    assert "They are not a diagnosis." in templates.provisional_next_step


def test_a_draft_cannot_approve_itself_and_a_broken_draft_is_refused():
    with pytest.raises(ValidationError):
        _changed(lambda plain: plain.update(status="approved"))

    def missing_text(plain):
        plain["texts"].pop()

    def unconfirmed_number(plain):
        plain["texts"][0]["text"] += " Or call 108."

    def a_diagnosis(plain):
        plain["texts"][0]["text"] += " Your diagnosis is a cold."

    def a_percentage(plain):
        plain["texts"][0]["text"] += " This is 80% likely."

    def no_reason(plain):
        plain["texts"][0]["why"] = " "

    for change, message in (
        (missing_text, "a release needs exactly these texts"),
        (unconfirmed_number, "which the owner has not confirmed"),
        (a_diagnosis, "no diagnosis and no percentage"),
        (a_percentage, "no diagnosis and no percentage"),
        (no_reason, "why it is worded so"),
    ):
        with pytest.raises(ResponseTextError, match=message):
            check_texts(_changed(change), {"112", "14416"})
    # A number counts only while the owner has confirmed it.
    with pytest.raises(ResponseTextError, match="which the owner has not confirmed"):
        check_texts(load_response_texts(), set())


def test_the_review_document_is_generated_from_the_draft_and_is_current():
    draft = load_response_texts()
    document = review_document(draft)
    assert (ROOT / "docs" / "review" / REVIEW_FILE).read_text(encoding="utf-8") == document
    assert "**Not approved. Not shown to anyone.**" in document and draft.label in document
    assert all(
        f"> {entry.text}" in document and entry.why in document and entry.shown_when in document
        for entry in draft.texts
    )
    assert document.count("**Owner's decision:**") == 4 and all(point in document for point in draft.open_points)
