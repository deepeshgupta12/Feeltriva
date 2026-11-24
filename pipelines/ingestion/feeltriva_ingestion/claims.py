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

Where a sentence ends is decided in `claim_sentences.py`. Both modules are pure: they read no file and no
database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .claim_sentences import _mask, sentences

# claims-2 (M2.6a): what ends a sentence after a single letter or an abbreviation.
# claims-3 (M2.6b): what is not an item of a list, after every stored list was read; more sentence ends.
# claims-4 (M2.6c): a text cut off by its source; a preposition after the lead-in; what a reviewer should check.
# claims-5 (M2.5e2): the number of words at which a source cuts its texts is measured for each source.
VERSION = "claims-5"
SENTENCE, LIST_ITEM = "sentence", "list_item"
MAX_ITEM_WORDS = 8  # a longer "item" is a clause, not an item of a list
MIN_WORDS_BEFORE_COLON = 3  # "B: Better ..." is a label; "There are three kinds: ..." is a lead-in
MIN_ITEMS = 3  # "A and B" is not split: two things joined by "and" are too often one thing

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


def split(text: str, cut_off_words: int | None = None) -> tuple[list[Claim], dict[str, int]]:
    """Every claim of a statement, sentences first and each sentence's list items after it, and why
    sentences with a comma were not split.

    `cut_off_words` is the number of words at which the statement's source cuts its texts (`measure_cut_off`), or
    0 for a source that cuts none. Left out, it is the limit of the one source measured by hand (`CUT_OFF_WORDS`)."""
    limit = CUT_OFF_WORDS if cut_off_words is None else cut_off_words
    claims: list[Claim] = []
    reasons: dict[str, int] = {}
    spans = sentences(text)
    for number, (start, end) in enumerate(spans):
        noticed = cues(text[start:end])
        items, reason = list_items(text, start, end)
        if number == len(spans) - 1 and _cut_off(text, limit):
            # The source cut the text here: the sentence is not whole, and the last item of its list is a fragment.
            noticed = {**noticed, "cut_off": [f"{limit} words"]}
            items = items[:-1]
        claims.append(Claim(SENTENCE, start, end, text[start:end], f"{VERSION}:sentence", None, noticed))
        if reason and reason != "no comma":
            reasons[reason] = reasons.get(reason, 0) + 1
        listed = {**noticed, **_first_item_cue(text, items)}
        for begin, finish in items:
            claims.append(
                Claim(LIST_ITEM, begin, finish, text[begin:finish], f"{VERSION}:enumeration", (start, end), listed)
            )
    return claims, reasons


def item_name(text: str) -> str:
    """A list item as a plain name, for comparing with a feature name: no remark in brackets, no article."""
    words = re.sub(r"[^a-z0-9]+", " ", _mask(text).replace("_", " ").lower()).split()
    if words and words[0] in ("a", "an", "the"):
        words = words[1:]
    return " ".join(words)


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
_PREPOSITIONS = (
    "in|on|at|of|with|without|within|between|among|through|during|before|after|along|around|behind|under|over|"
    "above|below|by|from|for|into|onto|upon|near|across|against|about|outside|inside|beyond"
)
_PREPOSITION = re.compile(rf"(?:{_PREPOSITIONS})\s", re.IGNORECASE)
_PREPOSITION_INSIDE = re.compile(rf"\s({_PREPOSITIONS}|to)\s", re.IGNORECASE)
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
    lead = _PREPOSITION.match(text[items[0][0] : items[0][1]])
    if lead and not any(_PREPOSITION.match(_bare(text[a:b])) for a, b in items[1:]):
        # "such as from lung, breast, thyroid, ...": the preposition goes with the lead-in; the item begins after it
        items = [_trim(text, items[0][0] + lead.end(), items[0][1]), *items[1:]]
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
    bare = [_bare(piece) for piece in pieces]
    if any(_GOES_ON.match(piece) for piece in bare):
        return [], "an item goes on with the item before it"
    led = [bool(_PREPOSITION.match(piece)) for piece in bare]
    if 0 < sum(led) < len(bare) - 1:  # all, or all but one: a list of places or times ("the wrists, between fingers")
        return [], "an item begins with a preposition"
    if not led[0] and all(led[1:]) and _PREPOSITION_INSIDE.search(_mask(pieces[0])):
        # "fat pads along the collarbone, on the back of the neck, and on the face": places of the one first item
        return [], "the other items go on with the first item"
    if any(_clause_at(found)[0] is not None for found in words):
        return [], "an item holds a clause"  # "dehydration, peripheral pulse is rapid, and ..."
    if len(words[-1]) > 1:
        alone = [found[1:] if found[0][1] in _ARTICLE else found for found in words[:-1]]
        first = words[0]
        # After "feeling tired", "weak" goes on with "feeling", not with the noun of the last item.
        after_a_verb = len(first) > 1 and first[0][1].endswith("ing")
        if (not after_a_verb and any(len(found) == 1 and found[0][1] in _DESCRIBING for found in alone)) or (
            len(first) > 1 and first[-1][1] in _DESCRIBING and first[-2][1] in _BEFORE_A_DESCRIPTION
        ):
            return [], "the items share one noun"  # "a mix of genetic, environmental, and neurological factors"
    return items, ""


# The source diseases_main.csv cuts its descriptions at 120 words: all 85 of them have exactly 120 words, and 79
# end without a full stop (measured in M2.6c). No other stored statement has 120 words and no full stop at its end.
CUT_OFF_WORDS = 120
_ENDS = re.compile(r"[.!?][\"')\]]*\s*$")


def _cut_off(text: str, limit: int) -> bool:
    """Whether the text was cut off by its source: it has exactly the source's limit of words and no full stop."""
    return limit > 0 and len(text.split()) == limit and not _ENDS.search(text)


def _bare(piece: str) -> str:
    """An item without the words that may stand before it ("occasionally", "in rare cases")."""
    return _PREFIX.sub("", piece, count=1) if _PREFIX.match(piece) else piece


def _first_item_cue(text: str, items: list[tuple[int, int]]) -> dict[str, Any]:
    """What a reviewer of a list should check, when the first item holds a preposition.

    "infection with viruses, bacteria, fungi" and "loss of appetite, nausea, vomiting" have the same wording: in
    the first the other items share the first words of the first item, in the second they do not. Only the
    meaning tells them apart, so the wording is recorded and nothing is decided."""
    if not items:
        return {}
    found = sorted({match.group(1).lower() for match in _PREPOSITION_INSIDE.finditer(_mask(text[slice(*items[0])]))})
    return {"first_item_preposition": found} if found else {}


# Found by measurement, before the texts of a source are split (decision E74). A source that cuts its texts at a
# number of words leaves a mark: no text is longer than the limit, several texts have exactly that length, and
# most of those stop in the middle of a sentence. `diseases_main.csv` shows it at 120 words (85 texts, 79 of them
# unfinished). Fewer than five texts at the longest length, or mostly finished ones, is no sign of a limit.
MIN_TEXTS_AT_A_LIMIT = 5


def measure_cut_off(texts: list[str]) -> int:
    """The number of words at which a source cut its texts, or 0 when the texts show no such limit."""
    lengths = [len(text.split()) for text in texts]
    if not lengths:
        return 0
    longest = max(lengths)
    at_the_limit = [text for text, length in zip(texts, lengths, strict=True) if length == longest]
    unfinished = sum(1 for text in at_the_limit if not _ENDS.search(text))
    return longest if len(at_the_limit) >= MIN_TEXTS_AT_A_LIMIT and unfinished * 2 > len(at_the_limit) else 0
