"""Where a sentence of a narrative statement ends (M2.6, M2.6a, M2.6b): the rules.

Every sentence of a stored statement is a claim (`claims.py`), so the ends of sentences decide what the
claims are. A full stop ends a sentence unless it belongs to an abbreviation or an initial; brackets are
masked first, so a full stop inside a remark in brackets ends nothing.

These rules were part of `claims.py` until M2.6c and were moved here unchanged, because the code index
cannot read a source file larger than 32 KB.

This module is pure: it reads no file and no database.
"""

from __future__ import annotations

import re

# A full stop after one of these is not the end of a sentence. "etc" is not listed: a full stop after it is
# looked at only when a capital or a digit follows, and there it ends the sentence ("the lips, tongue, etc. The").
_ABBREVIATIONS = frozenset(
    "e.g i.e vs dr mr mrs ms prof st fig no approx al ca cf inc ltd jr sr vol pp sp spp var incl".split()
)
_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
# The word before a full stop. Only a whole word counts: the letters that end a token of letters and
# digits ("794f", "2a") are not a word, so such a token ends its sentence (BUG-023).
_WORD_BEFORE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z.]+)$")


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
        if _continues(masked[start : match.start()], masked[match.end() :]):
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


# Words after which a single capital is a label and not an initial: "vitamin C.", "type B.", "hepatitis A.".
_LETTERED = frozenset(
    "vitamin vitamins hepatitis influenza type types subtype subtypes group groups class classes grade grades "
    "stage stages category categories strain strains serotype serotypes serogroup serogroups form forms variant "
    "variants level levels phase phases".split()
)
_PREVIOUS_WORD = re.compile(r"([A-Za-z]+)\s+$")


def _continues(before: str, after: str = "") -> bool:
    """Whether the full stop between `before` and `after` belongs to an abbreviation or an initial, so the
    sentence goes on.

    It is asked only where a capital or a digit follows the full stop. Measured on the stored statements (M2.6a):
    the first rule kept every single letter and every listed abbreviation inside its sentence, and ten pairs of
    real sentences stayed together. A single capital is taken for an initial ("J. Example", "B. Example") unless
    it is plainly something else. In this order:

    - a lower-case letter ("lower case d.") or the end of a unit joined by a sign ("mmol/L.", "40 °C.") ends;
    - one of several initials ("J. K. Example") goes on;
    - before a word that opens a sentence and is never a name ("plan B. Then ...") it ends;
    - after "and" or "or" it ends when it is the last of a series of letters ("A, B, and D."), and goes on
      when it is not ("Smith and J. Example");
    - after a word that takes a letter as a label ("vitamin C."), or after any other word in lower case that
      does not usually stand before a name ("plan B."), it ends. After "by", "of", "from" and the like, after a
      capitalised word, and where nothing stands before it, it is an initial.

    A listed abbreviation is written in lower case or with one capital ("No.", "Ms."); the same letters all in
    capitals are an acronym ("MS.") and end the sentence. "No." is the abbreviation only before a digit."""
    found = _WORD_BEFORE.search(before)
    if not found:
        return False
    word, after = found.group(1), after.lstrip("\"'_([ ")
    if len(word) > 1:
        plain = word.lower().rstrip(".")
        if plain == "no":
            return not word.isupper() and after[:1].isdigit()
        return plain in _ABBREVIATIONS and not word.isupper()
    head = before[: found.start(1)]
    if word.islower() or head.endswith(("/", "°")):
        return False
    if _INITIAL_BEFORE.search(head) or _INITIAL_AFTER.match(after):
        return True
    if _OPENER.match(after):
        return False
    previous = _PREVIOUS_WORD.search(head)
    if not previous:
        return True
    last = previous.group(1)
    if last.lower() in ("and", "or"):
        return not _SERIES_BEFORE.search(head)
    if last.lower() in _LETTERED:
        return False
    return not last.islower() or last in _BEFORE_A_NAME


_INITIAL_BEFORE = re.compile(r"(?<![A-Za-z0-9])[A-Z]\.\s*$")
_INITIAL_AFTER = re.compile(r"[A-Z]\.(?:\s|$)")
_SERIES_BEFORE = re.compile(r"(?<![A-Za-z0-9])[A-Z],?\s+(?:and|or)\s+$")
# Words that open a sentence and are never a name.
_OPENER = re.compile(
    r"(?:The|This|These|Those|It|Its|They|Their|He|She|His|Her|We|Our|There|Then|Thus|Therefore|However|Moreover|"
    r"Furthermore|Also|In|On|At|For|From|With|Without|By|As|If|When|While|Where|After|Before|During|Since|Until|"
    r"Although|Though|Because|But|And|Or|So|Yet|Some|Many|Most|Other|Others|Another|Each|Every|All|Both|Such|No|"
    r"Not|A|An)\b"
)
# Words in lower case after which a single capital is still an initial: "by J. Example", "the bacterium B. Example".
_BEFORE_A_NAME = frozenset(
    "by with of from to after see per named bacterium bacteria species genus organism pathogen parasite fungus".split()
)
