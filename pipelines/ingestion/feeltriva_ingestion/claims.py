"""Splitting a narrative statement into single claims with exact text spans (M2.6): the rules.

The handoff asks that atomic claims be extracted "only into a review queue", with source spans.
A claim here is a piece of a stored statement, never new wording:

- every sentence of the statement is a claim;
- where a sentence is a plain enumeration with a recognisable lead-in ("symptoms include A, B
  and C"), each item is a claim of its own, belonging to its sentence.

Each claim is the statement's text between two offsets, so a reviewer always sees the original.
Wording cues are recorded beside a claim (a negation word, a hedge such as "may", a word naming
a group of people). They say what the sentence contains; they are not a judgement, and a claim's
applicability stays empty until a reviewer sets it.

The rules are deliberately narrow. A sentence that is not clearly an enumeration is left whole.
Nothing here is medical knowledge, and nothing it produces is approved.

This module is pure: it reads no file and no database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

VERSION = "claims-2"  # claims-2 (M2.6a): what ends a sentence after a single letter or an abbreviation
SENTENCE, LIST_ITEM = "sentence", "list_item"
MAX_ITEM_WORDS = 8  # a longer "item" is a clause, not an item of a list
MIN_WORDS_BEFORE_COLON = 3  # "B: Better ..." is a label; "There are three kinds: ..." is a lead-in
MIN_ITEMS = 3  # "A and B" is not split: two things joined by "and" are too often one thing

# A full stop after one of these is not the end of a sentence. "etc" is not listed: a full stop after it is
# looked at only when a capital or a digit follows, and there it ends the sentence ("the lips, tongue, etc. The").
_ABBREVIATIONS = frozenset(
    "e.g i.e vs dr mr mrs ms prof st fig no approx al ca cf inc ltd jr sr vol pp sp spp var incl".split()
)
_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
# The word before a full stop. Only a whole word counts: the letters that end a token of letters and
# digits ("794f", "2a") are not a word, so such a token ends its sentence (BUG-023).
_WORD_BEFORE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z.]+)$")
# What introduces an enumeration. A strong lead-in may stand in any part of the sentence; a weak
# one ("is", "are") counts only in the first part, where it cannot be a clause inside an item.
_STRONG = re.compile(
    r"\b(?:includes?|included|including|such as|namely|caused by|due to|consists? of|characteri[sz]ed by|"
    r"treated with|associated with|results? from|ranges? from)\s+|:\s+|\b(?:e\.g\.|i\.e\.),?\s+",
    re.IGNORECASE,
)
_WEAK = re.compile(r"\b(?:are|is|were|was|be)\s+", re.IGNORECASE)
# "is" and "are" introduce a list only when the sentence is about a plural of things that get listed, and
# what follows is not a verb form ("are described in terms of ..."). Measured on the stored statements:
# without these two conditions "X is an emergency, requiring A and B" was cut into three items.
_LISTED_THINGS = re.compile(
    r"\b(?:symptoms|signs|features|manifestations|complications|causes|factors|types|forms|kinds|examples|"
    r"treatments|options|medications|medicines|drugs|therapies|effects|measures|methods|categories|stages)\b",
    re.IGNORECASE,
)
_VERB_FORM = re.compile(
    r"^(?:\w+ed|\w+ly|known|seen|found|given|thought|said|made|taken|shown|not|also|often|more|most|"
    r"less|very|quite)\b",
    re.IGNORECASE,
)
_CONJUNCTION = re.compile(r"\s(?:and|or)\s", re.IGNORECASE)
_LEADING_CONJUNCTION = re.compile(r"^(?:and|or|as well as)\s+", re.IGNORECASE)
# An "item" that begins like this is the start of a clause, so the sentence is not a plain list.
_CLAUSE_START = re.compile(
    r"^(?:may|can|could|might|should|will|would|is|are|was|were|has|have|had|which|that|who|whom|whose|when|"
    r"where|while|but|although|though|because|if|it|this|these|those|they|there|then|so|however)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(no|not|never|without|absent|absence of|rarely|neither|nor|free of|lack of|rule out|ruled out)\b", re.I
)
_HEDGE = re.compile(
    r"\b(may|might|can|could|sometimes|often|usually|typically|commonly|occasionally|generally|possibly|probably|"
    r"likely|tends? to|in some cases|in most cases)\b",
    re.I,
)
_POPULATION = re.compile(
    r"\b(children|child|infants?|newborns?|babies|adolescents?|teenagers?|adults?|elderly|older (?:people|adults)|"
    r"women|men|females?|males?|pregnan(?:t|cy)|girls?|boys?)\b",
    re.I,
)


@dataclass(frozen=True)
class Claim:
    kind: str  # sentence or list_item
    start: int
    end: int
    text: str  # exactly the statement's text between start and end
    rule: str
    parent: tuple[int, int] | None = None  # the span of the sentence a list item belongs to
    cues: dict[str, Any] = field(default_factory=dict)


def _mask(text: str) -> str:
    """The text with everything inside brackets replaced by underscores, same length: commas and
    full stops inside a remark in brackets do not split anything."""
    out, depth = [], 0
    for char in text:
        if char in "([":
            depth += 1
            out.append("_")
        elif char in ")]":
            depth = max(0, depth - 1)
            out.append("_")
        else:
            out.append("_" if depth else char)
    return "".join(out)


def sentences(text: str) -> list[tuple[int, int]]:
    """Spans of the sentences of a text. Together they hold every character that is not white space."""
    masked, spans, start = _mask(text), [], 0
    for match in _BOUNDARY.finditer(masked):
        if _continues(masked[start : match.start()]):
            continue  # an abbreviation, or an initial such as the "B." of "B. Example"
        end = match.start() + len(match.group().rstrip())
        spans.append((start, end))
        start = match.end()
    spans.append((start, len(text)))
    trimmed = []
    for begin, end in spans:
        piece = text[begin:end]
        left, right = len(piece) - len(piece.lstrip()), len(piece.rstrip())
        if right > left:
            trimmed.append((begin + left, begin + right))
    return trimmed


def _trim(text: str, begin: int, end: int) -> tuple[int, int]:
    while begin < end and text[begin].isspace():
        begin += 1
    while end > begin and (text[end - 1].isspace() or text[end - 1] in ".!?;:,"):
        end -= 1
    return begin, end


def _enumeration(text: str, start: int, end: int) -> tuple[list[tuple[int, int]], str]:
    """Spans of the items of the enumeration in the sentence text[start:end], and why there are none.

    Accepted only when the sentence has at least one comma outside brackets, ends in "and" or "or"
    before its last item, has a lead-in before its first item, and every item is short and does
    not begin like a clause."""
    masked = _mask(text[start:end])
    commas = [i for i, char in enumerate(masked) if char == ","]
    if not commas:
        return [], "no comma"
    bounds = [0, *[i + 1 for i in commas], len(masked)]
    parts = [(bounds[i], bounds[i + 1] - (1 if i < len(commas) else 0)) for i in range(len(bounds) - 1)]
    last_begin, last_end = parts[-1]
    last = masked[last_begin:last_end]
    oxford = _LEADING_CONJUNCTION.match(last.lstrip())
    if oxford:
        offset = len(last) - len(last.lstrip()) + oxford.end()
        tail = [(last_begin + offset, last_end)]
    else:
        joins = list(_CONJUNCTION.finditer(last))
        if not joins:
            return [], "no final 'and' or 'or'"
        if len(joins) > 1:  # "A, B and C such as D or E": where the last item begins cannot be told
            return [], "the end of the list is not clear"
        tail = [(last_begin, last_begin + joins[-1].start()), (last_begin + joins[-1].end(), last_end)]
    # Where the list begins: the last part, counted from the end, that holds a lead-in and leaves enough items.
    starts = []
    for index, (begin, finish) in enumerate(parts[:-1]):
        found = [
            match
            for match in _STRONG.finditer(masked[begin:finish])
            if not match.group().startswith(":")
            or len(masked[begin : begin + match.start()].split()) >= MIN_WORDS_BEFORE_COLON
        ]
        if not found and index == 0:
            weak = list(_WEAK.finditer(masked[begin:finish]))
            subject_lists = weak and _LISTED_THINGS.search(masked[begin : begin + weak[-1].start()])
            if subject_lists and not _VERB_FORM.match(masked[begin + weak[-1].end() : finish].lstrip()):
                found = weak
        if found:
            starts.append((index, begin + found[-1].end()))
    if not starts:
        return [], "no lead-in"
    reason = "fewer than three items"
    for index, first_begin in reversed(starts):
        spans = [(first_begin, parts[index][1]), *parts[index + 1 : -1], *tail]
        items = [_trim(text, start + begin, start + finish) for begin, finish in spans]
        if len(items) < MIN_ITEMS:
            continue
        words = [len(_mask(text[begin:finish]).replace("_", " ").split()) for begin, finish in items]
        if any(count == 0 or count > MAX_ITEM_WORDS for count in words):
            reason = "an item is empty or longer than a list item"
            continue
        if any(_CLAUSE_START.match(text[begin:finish]) for begin, finish in items):
            reason = "an item begins like a clause"
            continue
        if any(_LEADING_CONJUNCTION.match(text[begin:finish]) for begin, finish in items[:-1]):
            reason = "a list inside the list"  # "red, itchy, and watery eyes, and swelling": the parts are not items
            continue
        return items, ""
    return [], reason


def list_items(text: str, start: int, end: int) -> tuple[list[tuple[int, int]], str]:
    """Spans of the items of the enumeration in the sentence text[start:end], and why there are none.

    A semicolon outside brackets divides the sentence: an enumeration is looked for in each part, the last
    part first, so that "A, B, and C; then something else" does not carry the rest into its last item."""
    masked = _mask(text[start:end])
    cuts = [-1, *[i for i, char in enumerate(masked) if char == ";"], len(masked)]
    reason = "no comma"
    for index in range(len(cuts) - 2, -1, -1):
        items, why = _enumeration(text, start + cuts[index] + 1, start + cuts[index + 1])
        if items:
            return items, ""
        if why != "no comma":
            reason = why
    return [], reason


def cues(sentence: str) -> dict[str, Any]:
    """Words of the sentence that a reviewer should notice. What the wording contains, not what it means."""
    found: dict[str, Any] = {}
    for name, pattern in (("negation", _NEGATION), ("hedge", _HEDGE), ("population", _POPULATION)):
        words = sorted({match.group(1).lower() for match in pattern.finditer(sentence)})
        if words:
            found[name] = words
    return found


def split(text: str) -> tuple[list[Claim], dict[str, int]]:
    """Every claim of a statement, sentences first and each sentence's list items after it, and why
    sentences with a comma were not split."""
    claims: list[Claim] = []
    reasons: dict[str, int] = {}
    for start, end in sentences(text):
        noticed = cues(text[start:end])
        claims.append(Claim(SENTENCE, start, end, text[start:end], f"{VERSION}:sentence", None, noticed))
        items, reason = list_items(text, start, end)
        if reason and reason != "no comma":
            reasons[reason] = reasons.get(reason, 0) + 1
        for begin, finish in items:
            claims.append(
                Claim(LIST_ITEM, begin, finish, text[begin:finish], f"{VERSION}:enumeration", (start, end), noticed)
            )
    return claims, reasons


def item_name(text: str) -> str:
    """A list item as a plain name, for comparing with a feature name: no remark in brackets, no article."""
    words = re.sub(r"[^a-z0-9]+", " ", _mask(text).replace("_", " ").lower()).split()
    if words and words[0] in ("a", "an", "the"):
        words = words[1:]
    return " ".join(words)


# Words after which a single capital is a label and not an initial: "vitamin C.", "type B.", "hepatitis A.".
_LETTERED = frozenset(
    "vitamin vitamins hepatitis influenza type types subtype subtypes group groups class classes grade grades "
    "stage stages category categories strain strains serotype serotypes serogroup serogroups form forms variant "
    "variants level levels phase phases".split()
)
_PREVIOUS_WORD = re.compile(r"([A-Za-z]+)\s+$")


def _continues(before: str) -> bool:
    """Whether the full stop after this text belongs to an abbreviation or an initial, so the sentence goes on.

    It is asked only where a capital or a digit follows the full stop. Measured on the stored statements (M2.6a):
    the earlier rule kept every single letter and every listed abbreviation inside its sentence, and ten pairs of
    real sentences stayed together. A single letter is taken for an initial ("J. Example", "B. Example") unless it is
    plainly something else: a lower-case letter ("lower case d."), the end of a unit or label joined by a sign
    ("mmol/L.", "40 °C."), the last of a series ("A, B, C, and D.") or a label after a word that takes one
    ("vitamin C."). A listed abbreviation is written in lower case or with one capital ("No.", "Ms."); the same
    letters all in capitals are an acronym ("MS.") and end the sentence."""
    found = _WORD_BEFORE.search(before)
    if not found:
        return False
    word = found.group(1)
    if len(word) > 1:
        return word.lower().rstrip(".") in _ABBREVIATIONS and not word.isupper()
    head = before[: found.start(1)]
    if word.islower() or head.endswith(("/", "°")):
        return False
    previous = _PREVIOUS_WORD.search(head)
    return not (previous and previous.group(1).lower() in _LETTERED | {"and", "or"})
