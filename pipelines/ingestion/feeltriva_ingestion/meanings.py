"""Feature meanings derived from the supplied data (M2.7, owner decision E34): the rules.

For every dataset column and list term this module proposes

- a kind (`symptom`, `history`, `risk_factor`, `measurement`), or says the wording cannot settle it;
- what a zero in the column means, as far as the files themselves show it.

Every proposal carries the rule that produced it and a plain-language basis. Nothing here is
clinical knowledge beyond reading what a heading says, and nothing is approved: proposals are
stored as `pending` and a reviewer decides. What the data cannot settle is listed, not guessed.

Rules that follow from the handoff (`docs/01` section 4):

- "Do not treat a history question as an active symptom": the rules that recognise relatives,
  the past, a known diagnosis, treatment, exposure or lifestyle run before any symptom rule.
- "A blank matrix value, an imported zero and an explicit denial are different concepts": a
  zero is never proposed to mean a denial. No file contains a recorded denial.
- The kind `sign` is never proposed: no source separates what a person reports from what an
  examiner finds.

This module is pure: it reads no file and no database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION = "meanings-1"
UNDECIDED = "undecided"
# Zero meanings that may be proposed. `absent` (a recorded denial) is deliberately not among them.
ZERO_UNKNOWN, ZERO_NOT_RECORDED, ZERO_NO_ANSWER = "unknown", "not_recorded", "no_answer"

_QUESTION = re.compile(r"^e[ _]\d+[ _]")
# A truncated question ends in a word that needs an object ("have you recently had a ...").
_DANGLING = {"a", "an", "the", "of", "or", "and", "in", "to", "that", "you", "your", "for", "with", "at", "on"}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str
    pattern: re.Pattern[str]
    basis: str


def _rule(rule_id: str, kind: str, pattern: str, basis: str) -> Rule:
    return Rule(rule_id, kind, re.compile(pattern), basis)


# Ordered: the first rule that matches decides. Everything before the symptom rules exists so
# that a question about relatives, the past, a diagnosis, a treatment or an exposure can never
# be read as a present symptom.
WORDING_RULES: tuple[Rule, ...] = (
    _rule(
        "relatives",
        "history",
        r"\b(family|mother|father|relatives?)\b|\bmembers? of\b|\bany member\b",
        "the wording is about relatives, not about the person's own present state",
    ),
    _rule(
        "exposure_or_lifestyle",
        "risk_factor",
        r"\b(smoke|smoker|smoking|secondhand|alcohol|coffee|energy drinks|exercise regularly|work in|live in|live with"
        r"|attend or work|traveled|in contact|contacts|exposed|unprotected sex|sexual intercourse|eat"
        r"|descent|overweight|intravenous|drug abuse|transfusion|injections|consumption)\b",
        "the wording names a habit, an exposure, a living or working condition or a descent",
    ),
    _rule(
        "body_measure",
        "measurement",
        r"\bbmi\b",
        "the wording names a measured quantity",
    ),
    _rule(
        "past_event",
        "history",
        r"^(have|did|were) you ever\b|\bever (had|been|felt)\b|\bhistory\b|\bformer\b|\bdiagnosed\b"
        r"|\bhospitalized\b|\bsurgery\b|\bbreastfed\b"
        r"|\bvaccinations?\b|^were you born\b|^did you have your first\b",
        "the wording asks about the past (ever, diagnosed, surgery, born, first, vaccinations)",
    ),
    _rule(
        "known_condition",
        "history",
        r"\bknown\b|\bsuffer from\b|\bchronic\b|\bimmunosuppressed\b|\binfected with\b|\bmetastatic\b"
        r"|^do you have (diabetes|heart failure|asthma|liver cirrhosis|rheumatoid arthritis|parkinsons disease"
        r"|cystic fibrosis|high cholesterol|polyps)\b",
        "the wording names a standing diagnosis or says known, chronic or suffer from",
    ),
    _rule(
        "treatment",
        "history",
        r"\b(treated|taking|take|taken|medication|hormones|corticosteroids|dialysis|stimulant|decongestan\w*)\b",
        "the wording asks about treatment or medication",
    ),
    _rule(
        "description_of_a_symptom",
        "symptom",
        r"^(what|where|how|characterize)\b",
        "the wording asks to describe a symptom (what, where, how); it is not a yes/no question",
    ),
    _rule(
        "about_a_named_symptom",
        "symptom",
        r"\b(the|your) (pain|rash|lesions?|swelling|itching|symptoms)\b",
        "the wording refers to a symptom it names (the pain, the rash, your lesions, your symptoms)",
    ),
    _rule(
        "present_experience",
        "symptom",
        r"^(do you (constantly |suddenly |ever )?feel|are you feeling|are you experiencing|have you noticed|have you lost"
        r"|did you lose|did you vomit|have you vomited|have you been coughing|do you wheeze|do you have symptoms"
        r"|do you have pain|have you felt|are you unable)\b|\b(difficulty|trouble)\b",
        "the wording asks about something the person feels, notices or cannot do, now or recently",
    ),
)


@dataclass(frozen=True)
class KindProposal:
    kind: str  # a feature kind, or UNDECIDED
    rule: str
    basis: str
    reason_undecided: str = ""


def readable(heading: str) -> str:
    """A heading as plain lower-case words: `E_91_do_you_have_a_fever` -> `do you have a fever`."""
    text = " ".join(heading.lower().replace("_", " ").split())
    return _QUESTION.sub("", text)


def is_question(heading: str) -> bool:
    return bool(_QUESTION.match(heading.lower()))


def is_cut_off(heading: str) -> bool:
    """A question whose last word needs an object: the source file stores it truncated."""
    words = readable(heading).split()
    return is_question(heading) and bool(words) and words[-1] in _DANGLING


def classify_kind(heading: str, source_says_symptom: str, symptom_terms: frozenset[str]) -> KindProposal:
    """Kind of one column or list term.

    source_says_symptom: how the source itself presents the column as a symptom (a column
    prefix, the name of the list column, the file name), or "" when it does not.
    symptom_terms: terms that other sources present as symptoms, used to recognise a symptom
    named inside a question ("do you have a cough").
    """
    text = readable(heading)
    for rule in WORDING_RULES:
        if rule.pattern.search(text):
            basis = rule.basis
            if rule.kind != "symptom" and source_says_symptom:
                basis += f"; the source presents it as a symptom ({source_says_symptom}), the wording decides"
            return KindProposal(rule.kind, rule.rule_id, basis)
    if is_question(heading):
        named = sorted((term for term in symptom_terms if re.search(rf"\b{re.escape(term)}\b", text)), key=len)
        if named:
            return KindProposal(
                "symptom",
                "names_a_symptom",
                f"the question names '{named[-1]}', which another source presents as a symptom",
            )
        reason = (
            "the question is cut off in the source file before its object"
            if is_cut_off(heading)
            else "no rule recognises the wording"
        )
        return KindProposal(UNDECIDED, "none", "", reason)
    if source_says_symptom:
        return KindProposal(
            "symptom",
            "stated_by_source",
            f"the source presents it as a symptom ({source_says_symptom}) and the wording names no history, "
            "exposure or measurement",
        )
    return KindProposal(UNDECIDED, "none", "", "the source does not say what the column is")


@dataclass(frozen=True)
class ZeroProposal:
    zero: str
    rule: str
    basis: str


def classify_zero(
    *,
    is_list_term: bool,
    always_affirmed: bool,
    identical_group: tuple[str, ...],
    describes_a_symptom: bool,
    same_cases_as_lists: str,
) -> ZeroProposal:
    """What a zero in the column means, from what the files show. Never a denial.

    always_affirmed: the column is 1 in every row. identical_group: other columns of the file
    that are 1 in exactly the same rows. same_cases_as_lists: the list file of the same archive
    that holds the same cases as lists of affirmed terms, or "".
    """
    if is_list_term:
        return ZeroProposal(
            ZERO_NOT_RECORDED,
            "list_term",
            "a list only names what is affirmed; a term that is not listed was not recorded",
        )
    if always_affirmed:
        return ZeroProposal(
            ZERO_NO_ANSWER,
            "affirmed_in_every_row",
            "the column is 1 in every row, so 1 cannot mean yes: it marks that an answer was recorded, and the "
            "answer itself is not in the file",
        )
    if identical_group:
        return ZeroProposal(
            ZERO_NO_ANSWER,
            "recorded_together",
            f"the column is 1 in exactly the same rows as {len(identical_group)} other column(s) "
            f"({', '.join(identical_group[:3])}{', ...' if len(identical_group) > 3 else ''}): the questions were "
            "answered as one block, 1 marks that an answer was recorded, and the answer itself is not in the file",
        )
    if describes_a_symptom:
        return ZeroProposal(
            ZERO_NO_ANSWER,
            "description_question",
            "the question asks for a description, not yes or no; 1 marks that an answer was recorded",
        )
    if same_cases_as_lists:
        return ZeroProposal(
            ZERO_NOT_RECORDED,
            "same_cases_as_lists",
            f"the same cases exist in {same_cases_as_lists} as lists of affirmed terms only; a zero here is a term "
            "that was not listed",
        )
    return ZeroProposal(
        ZERO_UNKNOWN,
        "no_evidence",
        "the file shows only which columns are affirmed; nothing in it says whether a zero was asked and denied or "
        "never recorded",
    )


def propose_age_unit(minimum: float, maximum: float, whole_numbers: bool) -> tuple[str, str]:
    """(unit or UNDECIDED, basis). A reading of the value range, not source documentation."""
    described = f"values run from {minimum:g} to {maximum:g}" + (" in whole numbers" if whole_numbers else "")
    if whole_numbers and minimum >= 0 and 60 <= maximum <= 120:
        return (
            "years",
            f"{described}; that is the span of human ages counted in completed years, and no other common unit "
            "fits it. No source documentation states the unit",
        )
    return UNDECIDED, f"{described}; the range does not single out a unit and no source documentation states it"
