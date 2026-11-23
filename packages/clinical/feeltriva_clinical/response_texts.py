"""The draft response texts of a release (M2.5f1): reading them, checking them, writing them out.

Every release bundle carries four texts that a person is shown outside the rules: the request to
confirm what was understood, the next step above possible explanations, the text when no
explanation can be given, and the text when the assessment could not be completed. Owner decision
E81: the engineering assistant drafts them and the owner approves every word.

A draft is not approved. Its status can only be `pending`: the file cannot approve itself. A text
may name a telephone number only if the owner has confirmed that number in the urgency rule file.

This module is pure: it reads files of this package and no database.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .bundle import Templates
from .urgency_draft import load_draft

TEXTS_PATH = Path(__file__).parent / "drafts" / "response_texts_draft.json"
REVIEW_FILE = "response_texts_draft.md"
MIN_LENGTH, MAX_LENGTH = 40, 600
_NUMBER = re.compile(r"\b\d{3,}\b")


class ResponseTextError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseText(_Strict):
    key: str  # the name of the text in a release bundle
    shown_when: str
    text: str
    why: str


class ResponseTexts(_Strict):
    draft_id: str
    version: str
    status: Literal["pending"]
    label: str
    jurisdiction: str
    written: str
    texts: list[ResponseText]
    open_points: list[str]

    def as_templates(self) -> Templates:
        """The texts in the form a release bundle holds them."""
        return Templates(**{entry.key: entry.text for entry in self.texts})


def check_texts(draft: ResponseTexts, confirmed_numbers: set[str]) -> None:
    """Raise ResponseTextError unless the draft holds exactly the four texts, each in order."""
    keys = [entry.key for entry in draft.texts]
    if sorted(keys) != sorted(Templates.model_fields):
        raise ResponseTextError(f"a release needs exactly these texts: {sorted(Templates.model_fields)}")
    for entry in draft.texts:
        if not MIN_LENGTH <= len(entry.text) <= MAX_LENGTH:
            raise ResponseTextError(f"{entry.key}: the text has {len(entry.text)} characters")
        if not entry.shown_when.strip() or not entry.why.strip():
            raise ResponseTextError(f"{entry.key}: it does not say when it is shown, or why it is worded so")
        unknown = sorted(set(_NUMBER.findall(entry.text)) - confirmed_numbers)
        if unknown:
            raise ResponseTextError(f"{entry.key}: it names {unknown}, which the owner has not confirmed")
        lowered = entry.text.lower()
        if "%" in entry.text or ("diagnos" in lowered and "not a diagnosis" not in lowered):
            raise ResponseTextError(f"{entry.key}: a response text gives no diagnosis and no percentage")


def load_response_texts(path: Path = TEXTS_PATH) -> ResponseTexts:
    draft = ResponseTexts.model_validate(json.loads(path.read_text(encoding="utf-8")))
    check_texts(draft, {entry.number for entry in load_draft().numbers if entry.confirmed_by_owner})
    return draft


def review_document(draft: ResponseTexts) -> str:
    """The draft as a document for the owner. Generated: change the draft file, not this text."""
    lines = [
        "# Response texts: draft for the owner's approval",
        "",
        "> **Not approved. Not shown to anyone.**",
        f"> {draft.label}",
        "",
        f"Draft `{draft.version}` for {draft.jurisdiction}, written {draft.written}. This document is generated from "
        "`packages/clinical/feeltriva_clinical/drafts/response_texts_draft.json`: change the file, not this text.",
        "",
        "## What these texts are",
        "",
        "Every release carries four texts that a person is shown outside the urgency rules. The service never "
        "writes such a text itself: it shows exactly these words. None of them names an illness, a medicine or a "
        "percentage. The only telephone number they name is one the owner has confirmed.",
        "",
        "| No. | Text | Shown when |",
        "|---:|---|---|",
        *[f"| {number} | `{entry.key}` | {entry.shown_when} |" for number, entry in enumerate(draft.texts, 1)],
        "",
        "## The texts",
    ]
    for number, entry in enumerate(draft.texts, 1):
        lines += [
            "",
            f"### {number}. `{entry.key}`",
            "",
            f"**Shown when.** {entry.shown_when}",
            "",
            "**The person is shown**",
            "",
            f"> {entry.text}",
            "",
            f"**Why it is worded so.** {entry.why}",
            "",
            "**Owner's decision:** approve / change / reject. Note:",
        ]
    lines += ["", "## Still open", "", *[f"- {point}" for point in draft.open_points], ""]
    return "\n".join(lines)
