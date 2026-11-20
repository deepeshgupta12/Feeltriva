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

# claims-2 (M2.6a): what ends a sentence after a single letter or an abbreviation.
# claims-3 (M2.6b): what is not an item of a list, after every stored list was read; more sentence ends.
VERSION = "claims-3"
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
    r"where|while|but|although|though|because|if|it|this|these|those|they|there|then|so|however|whether|either|"
    r"also|rather|to)\b",
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
        if _PAIRED.search(last[: joins[-1].start()]):  # "the valve between the stomach and the duodenum"
            return [], "the last 'and' or 'or' belongs to 'between', 'either' or 'both'"
        tail = [(last_begin, last_begin + joins[-1].start()), (last_begin + joins[-1].end(), last_end)]
    # Where the list may begin: every part before the last that holds a lead-in.
    starts = []
    for index, (begin, finish) in enumerate(parts[:-1]):
        found = [
            match
            for match in _STRONG.finditer(masked[begin:finish])
            if not match.group().startswith(":")
            or len(masked[begin : begin + match.start()].split()) >= MIN_WORDS_BEFORE_COLON
        ]
        if not found and index == 0 and not _SUBORDINATE_START.match(masked.lstrip()):
            weak = list(_WEAK.finditer(masked[begin:finish]))
            subject_lists = weak and _LISTED_THINGS.search(masked[begin : begin + weak[-1].start()])
            if subject_lists and not _VERB_FORM.match(masked[begin + weak[-1].end() : finish].lstrip()):
                found = weak
        if found:
            lead = found[-1]
            subject = bool(
                _BEFORE_A_SUBJECT.match(lead.group()) or _RELATIVE_BEFORE.search(masked[begin : begin + lead.start()])
            )
            starts.append((index, begin + lead.end(), subject))
    if not starts:
        return [], "no lead-in"
    # The first lead-in that gives a list is taken: a later one stands inside an item ("a round red face due to
    # facial plethora, a fat lump ..."). Only where an item holds a lead-in that opens a list of its own ("fluids
    # such as water, juice, and broth") is the list after that lead-in taken, when there is one.
    reason, held = "fewer than three items", None
    for index, first_begin, subject in starts:
        spans = [(first_begin, parts[index][1]), *parts[index + 1 : -1], *tail]
        items = [_trim(text, start + begin, start + finish) for begin, finish in spans]
        if len(items) < MIN_ITEMS:
            continue
        items, why = _checked(text, items, subject)
        if why:
            reason = why
        elif any(_SUBLIST.search(text[begin:finish]) for begin, finish in items[:-1]):
            held = held or items
        else:
            return items, ""
    return (held, "") if held else ([], reason)


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

# What is not an item of a list (claims-3). Every stored list was read (628); each test below removes a kind of
# wrong list that was found, and the word lists are closed and about wording, not medicine.
_PAIRED = re.compile(r"\b(?:between|both|either|whether)\b", re.IGNORECASE)
# A sentence that opens with one of these has its "is" or "are" in a clause that only leads up to the main one:
# "Although few studies have shown to be helpful ..., some evidence shows ...".
_SUBORDINATE_START = re.compile(r"(?:although|though|while|whereas)\b", re.IGNORECASE)
# After these lead-ins the list can be the subject, and the sentence goes on with its verb after the last item:
# "symptoms such as A, B, and C may develop". After "include" or "are" the verb has been said already, so a verb
# after the last item opens a new clause: "Symptoms include A, B, and an examination may show ...".
_BEFORE_A_SUBJECT = re.compile(r"(?:such as|including|namely|e\.g|i\.e)", re.IGNORECASE)
_RELATIVE_BEFORE = re.compile(r"\b(?:which|that)\s+$", re.IGNORECASE)
_DASH = re.compile(r"—|\s[–-]\s")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_QUALIFYING = (
    "particularly|especially|typically|usually|commonly|mainly|mostly|primarily|generally|frequently|notably|"
    "predominantly|chiefly|often"
)
# An item that begins like this says more about the item before it: "fever, often greater than 40 °C, cough".
_QUALIFIER = re.compile(rf"(?:(?:most|more|less)\s+)?(?:{_QUALIFYING})\b", re.IGNORECASE)
# Words that may stand before an item without changing what it is: "and occasionally fever", "in rare cases coma".
_PREFIX = re.compile(
    rf"(?:(?:(?:most|more|less)\s+)?(?:{_QUALIFYING}|occasionally|sometimes|rarely|possibly|eventually|even)\s+|"
    r"in\s+(?:some|rare|severe|extreme|most|many|certain)\s+cases,?\s+)+",
    re.IGNORECASE,
)
_PREPOSITION = re.compile(
    r"(?:in|on|at|of|with|without|within|between|among|through|during|before|after|along|around|behind|under|over|"
    r"above|below|by|from|for|into|onto|upon|near|across|against|about|outside|inside|beyond)\s",
    re.IGNORECASE,
)
# An item that begins like this goes on with the item before it: "heart failure, due to ...", "..., leading to ...".
_GOES_ON = re.compile(
    r"(?:such as|including|includes?|namely|e\.g|i\.e|due to|secondary to|related to|leading to|"
    r"resulting (?:in|from)|ranging from|depending on|followed by|accompanied by|caused by|associated with|"
    r"characteri[sz]ed by|known as|referred to|prevalent in|occurring|lasting|causing|highlighting|indicating|"
    r"suggesting|reflecting|requiring|affecting|involving|called|termed|named)\b",
    re.IGNORECASE,
)
_SUBLIST = re.compile(r"\b(?:such as|including|includes?|namely)\b|\b(?:e\.g|i\.e)\.", re.IGNORECASE)
_JOINING = frozenset(
    "and or rather less more most commonly often rarely frequently occasionally sometimes usually typically generally "
    "eventually finally later also then possibly especially particularly notably".split()
)
_AUXILIARY = frozenset("may might can could will would should must is are was were has have had do does did".split())
# Verbs found after a list that stands as the subject: "factors such as A, B, and C play a role".
_PREDICATE = frozenset("appear appears play plays increase increases interact interacts".split())
_RELATIVE = frozenset("that which who whom whose like as than where".split())
_ADVERBIAL = frozenset("when if because while until although unless since".split())
_NOT_BEFORE_A_VERB = frozenset("to a an the no of in".split())
# Words that describe and do not name: as a whole item before a longer last item they share its noun
# ("a red, warm, swollen, and painful leg").
_DESCRIBING = frozenset(
    "red pink purple blue bluish yellow yellowish white pale dark brown black grey gray warm hot cool dry wet moist "
    "flaky scaly greasy oily itchy crusty rough smooth thick thin hard soft firm tender swollen painful stiff weak "
    "numb small large round flat raised sudden gradual sharp dull mild moderate severe acute subacute chronic "
    "recurrent persistent intermittent constant random jerky rapid slow irregular uncontrollable involuntary "
    "physical mental emotional psychological psychiatric cognitive behavioral behavioural social genetic "
    "environmental hormonal immune bacterial viral fungal neurological metabolic".split()
)
_ARTICLE = frozenset("a an the".split())
_BEFORE_A_DESCRIPTION = frozenset("a an the of in with and or".split())


def _words(text: str) -> list[tuple[int, str]]:
    """(offset, word in lower case) of the words of an item, without what stands in brackets."""
    return [(match.start(), match.group().lower()) for match in _WORD.finditer(_mask(text))]


def _clause_at(words: list[tuple[int, str]]) -> tuple[int | None, bool]:
    """Where an item turns into a clause (the offset of its verb), and whether a word such as "when" stands before.

    "Legionella may occur with abdominal pain" is a clause; "pain that is worse at night" and "feeling like one is
    going to pass out" are items that hold a clause of their own, and are left alone."""
    adverbial = False
    for index, (offset, word) in enumerate(words):
        if word in _RELATIVE:
            return None, False
        if word in _ADVERBIAL:
            adverbial = True
        elif index and words[index - 1][1] not in _NOT_BEFORE_A_VERB:
            if word in _AUXILIARY or (word in _PREDICATE and index < len(words) - 1):
                return offset, adverbial
    return None, False


def _checked(text: str, items: list[tuple[int, int]], subject: bool) -> tuple[list[tuple[int, int]], str]:
    """The items of a list as they may be stored (the last one shortened where the sentence goes on after it),
    or the reason why they are not the items of a list. `subject` says the list may be the subject of its sentence."""
    begin, finish = items[-1]
    dash = _DASH.search(text[begin:finish])
    if dash:  # "... and levodopa—the most widely used drug": the item ends where the remark begins
        finish = begin + dash.start()
    verb, adverbial = _clause_at(_words(text[begin:finish]))
    if subject and verb is not None and not adverbial:  # "... and feeling tired may develop"
        finish = begin + verb
    items = [*items[:-1], _trim(text, begin, finish)]
    pieces = [text[a:b] for a, b in items]
    words = [_words(piece) for piece in pieces]
    counts = [len(_mask(piece).replace("_", " ").split()) for piece in pieces]
    if any(not found for found in words) or any(count > MAX_ITEM_WORDS for count in counts):
        return [], "an item is empty or longer than a list item"
    if any(piece.count("(") != piece.count(")") or piece.count("[") != piece.count("]") for piece in pieces):
        return [], "a bracket is not closed"
    if any(_DASH.search(piece) for piece in pieces[:-1]):
        return [], "a remark after a dash"  # "impulsivity – failure to resist a temptation, an urge, or ..."
    if any(_CLAUSE_START.match(piece) for piece in pieces):
        return [], "an item begins like a clause"
    if any(_LEADING_CONJUNCTION.match(piece) for piece in pieces[:-1]):
        return [], "a list inside the list"  # "red, itchy, and watery eyes, and swelling": the parts are not items
    if any(all(word in _JOINING for _offset, word in found) for found in words):
        return [], "an item is only a joining word"  # "fever, and, less commonly, seizures"
    if any(_QUALIFIER.match(piece) for piece in pieces[1:-1]):
        return [], "an item says more about the item before it"
    bare = [_PREFIX.sub("", piece, count=1) if _PREFIX.match(piece) else piece for piece in pieces]
    if any(_GOES_ON.match(piece) for piece in bare):
        return [], "an item goes on with the item before it"
    led = sum(1 for piece in bare if _PREPOSITION.match(piece))
    if 0 < led < len(bare) - 1:  # all, or all but one: a list of places or times ("the wrists, between fingers, ...")
        return [], "an item begins with a preposition"
    if any(_clause_at(found)[0] is not None for found in words):
        return [], "an item holds a clause"  # "dehydration, peripheral pulse is rapid, and ..."
    if len(words[-1]) > 1:
        alone = [found[1:] if found[0][1] in _ARTICLE else found for found in words[:-1]]
        first = words[0]
        if any(len(found) == 1 and found[0][1] in _DESCRIBING for found in alone) or (
            len(first) > 1 and first[-1][1] in _DESCRIBING and first[-2][1] in _BEFORE_A_DESCRIPTION
        ):
            return [], "the items share one noun"  # "a mix of genetic, environmental, and neurological factors"
    return items, ""
