"""Splitting a statement into single claims with exact spans (M2.6): the rules. Invented sentences; no database."""

from __future__ import annotations

from feeltriva_ingestion.claims import (
    CUT_OFF_WORDS,
    LIST_ITEM,
    SENTENCE,
    VERSION,
    cues,
    item_name,
    list_items,
    sentences,
    split,
)


def _items(text):
    found, reason = list_items(text, 0, len(text))
    return [text[begin:end] for begin, end in found], reason


def test_sentences_hold_all_the_text_and_keep_their_exact_offsets():
    text = "  First thing happens. Then a second thing (with a remark. Inside brackets) follows!  Third one?  "
    spans = sentences(text)
    assert [text[begin:end] for begin, end in spans] == [
        "First thing happens.",
        "Then a second thing (with a remark. Inside brackets) follows!",  # a full stop inside brackets does not split
        "Third one?",
    ]
    assert "".join(text[begin:end] for begin, end in spans).replace(" ", "") == text.replace(" ", "")
    assert sentences("No full stop at the end") == [(0, 23)] and sentences("   ") == []


def test_an_abbreviation_or_a_single_letter_does_not_end_a_sentence():
    text = "Agents such as e.g. Alpha and Dr. Beta were named. The bacterium B. Example was found vs. Other ones."
    assert [text[begin:end] for begin, end in sentences(text)] == [
        "Agents such as e.g. Alpha and Dr. Beta were named.",
        "The bacterium B. Example was found vs. Other ones.",
    ]


def test_an_enumeration_with_a_lead_in_gives_one_claim_per_item():
    assert _items("Signs include a blue hat, a red scarf (worn loosely), green gloves and a coat.") == (
        ["a blue hat", "a red scarf (worn loosely)", "green gloves", "a coat"],
        "",
    )
    # With a comma before the last "and" too, and with "or"; a comma inside brackets is not a list comma.
    assert _items("They may be caused by rain, wind (strong, cold), or snow.")[0] == [
        "rain",
        "wind (strong, cold)",
        "snow",
    ]
    assert _items("There are three kinds: small, medium, and large.")[0] == ["small", "medium", "large"]
    # The list starts at a lead-in that leaves three items: here the one in the second part of the sentence.
    assert _items("Some can be taken by mouth, and these include alpha, beta, gamma and delta.")[0] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
    ]
    # An item may hold one example of its own; a lead-in that opens a list of its own is tested further down.
    assert _items("Signs include a hat, a scarf such as wool, and gloves.")[0] == [
        "a hat",
        "a scarf such as wool",
        "gloves",
    ]


def test_is_and_are_introduce_a_list_only_for_a_plural_of_listed_things_and_not_before_a_verb_form():
    assert _items("The main symptoms are a hat, a scarf, and gloves.")[0] == ["a hat", "a scarf", "gloves"]
    assert _items("The storm is a real emergency, requiring boats and potentially rescue.") == ([], "no lead-in")
    assert _items("Symptoms are described in terms of high, low, and middle ones.") == ([], "no lead-in")
    assert _items("The medications are generally aimed at warmth, good water, and rest.") == ([], "no lead-in")


def test_a_sentence_that_is_not_clearly_a_list_is_left_whole_and_says_why():
    assert _items("A hat is worn on the head.") == ([], "no comma")
    assert _items("Hats, scarves and gloves are common.") == ([], "no lead-in")
    assert _items("Signs include a hat, which is blue.") == ([], "no final 'and' or 'or'")
    assert _items("Signs include a hat, a scarf and gloves such as wool or silk ones.") == (
        [],
        "the end of the list is not clear",
    )
    assert _items("Signs include a hat and a scarf, or gloves.")[1] == "fewer than three items"
    assert _items("Signs include a hat, a scarf, and may need a coat.")[1] == "an item begins like a clause"
    assert _items("Signs include a hat, a scarf that nobody has ever seen in this town before, and gloves.")[1] == (
        "an item is empty or longer than a list item"
    )
    assert _items("Signs include a hat, red, soft, and warm gloves, and a coat.")[1] == "a list inside the list"


def test_a_semicolon_divides_the_sentence_and_a_short_label_before_a_colon_is_no_lead_in():
    # What follows the semicolon is not carried into the last item.
    assert _items("Severe signs include a hat, a scarf, and gloves; rain can follow.")[0] == [
        "a hat",
        "a scarf",
        "gloves",
    ]
    # The enumeration may also stand after the semicolon.
    assert _items("Care is given by teams; it is associated with warmth, comfort, and rest.")[0] == [
        "warmth",
        "comfort",
        "rest",
    ]
    assert _items("B: Better hats with soft, warm linings on cold days or wet days.") == ([], "no lead-in")
    assert _items("There are three kinds: small, medium, and large.")[0] == ["small", "medium", "large"]


def test_cues_say_what_the_wording_contains():
    assert cues("Children may not have signs for years, and rarely in women.") == {
        "negation": ["not", "rarely"],
        "hedge": ["may"],
        "population": ["children", "women"],
    }
    assert cues("A hat is worn on the head.") == {}


def test_every_claim_is_its_statement_s_own_text_and_a_list_item_belongs_to_its_sentence():
    text = "The thing is common. Signs may include a hat, a scarf (red), and gloves. It ends."
    claims, reasons = split(text)
    assert all(text[claim.start : claim.end] == claim.text for claim in claims)
    assert [(claim.kind, claim.text) for claim in claims] == [
        (SENTENCE, "The thing is common."),
        (SENTENCE, "Signs may include a hat, a scarf (red), and gloves."),
        (LIST_ITEM, "a hat"),
        (LIST_ITEM, "a scarf (red)"),
        (LIST_ITEM, "gloves"),
        (SENTENCE, "It ends."),
    ]
    sentence = claims[1]
    assert {claim.parent for claim in claims if claim.kind == LIST_ITEM} == {(sentence.start, sentence.end)}
    assert [claim.rule for claim in claims[1:3]] == [f"{VERSION}:sentence", f"{VERSION}:enumeration"]
    assert claims[2].cues == sentence.cues == {"hedge": ["may"]} and reasons == {}
    # Why a sentence with a comma was left whole is counted.
    assert split("Hats, scarves and gloves are common.")[1] == {"no lead-in": 1}


def test_an_item_is_compared_with_a_feature_name_without_its_article_and_bracket():
    assert item_name("a Red-Scarf (worn loosely)") == "red scarf"
    assert item_name("The hat") == "hat" and item_name("gloves") == "gloves"


def test_a_token_of_letters_and_digits_ends_its_sentence_whatever_its_last_letters_are():
    # BUG-023: the letters ending such a token were read as a single-letter word or an abbreviation,
    # so the sentence was not ended. The first text is the one a CI run failed on.
    text = "Signs may include a hat b7c75f794f, a scarf b7c75f794f (red), and gloves b7c75f794f. It ends."
    assert [text[start:end] for start, end in sentences(text)] == [text[:-9], "It ends."]
    for sample in ("The code is 794f. It ends.", "Fill in form 2a. Then sign it.", "It is model x9ca. Next one."):
        assert len(sentences(sample)) == 2, sample
    # A letter standing alone and a real abbreviation still do not end a sentence, also after a bracket or a hyphen.
    for sample in (
        "It was B. burgdorferi again.",
        "See e.g. Those listed.",
        "A cap (cf. Hats) fits.",
        "Type-B. Burgdorferi.",
    ):
        assert len(sentences(sample)) == 1, sample


def test_a_single_letter_or_an_abbreviation_that_plainly_ends_a_sentence_does_end_it():
    # M2.6a: measured on the stored statements, ten pairs of sentences were kept together by a single letter or
    # an abbreviation before the full stop. Invented sentences of the same shapes.
    for sample in (
        "They sell vitamin C. Early buyers get a hat.",  # a label after a word that takes one
        "There are four kinds of hat: types A, B, C, and D. Birds wear the first.",  # the last of a series
        "It comes as A or B. Then it is packed.",
        "The tank holds 135 units/L. Above that it spills.",  # the end of a unit joined by a sign
        "The oven goes from 37 °C to 40 °C. Then it cools.",
        "It is written with a lower case d. It later changed.",  # an initial is a capital
        "The club is called MS. Roughly half the town joined.",  # an acronym, not the title "Ms."
        "It covers hats, scarves, etc. The list goes on.",
    ):
        assert len(sentences(sample)) == 2, sample
    # An initial and an abbreviation written as one still do not end a sentence.
    for sample in (
        "The bacterium B. Example was found.",
        "It was seen by J. Example in May.",
        "She met Ms. Example and Dr. Other.",
        "It ranks No. 4 in the list.",
        "Tools of one kind i.e. ENT tools are listed.",
    ):
        assert len(sentences(sample)) == 1, sample
    # The series becomes a list once its sentence ends where it should.
    text = "There are four kinds of hat: types A, B, C, and D. Birds wear the first."
    assert [claim.text for claim in split(text)[0] if claim.kind == LIST_ITEM] == ["types A", "B", "C", "D"]


def test_what_is_not_an_item_of_a_list_is_refused_and_says_why():
    # M2.6b: every stored list was read (628); each case below is the shape of a wrong list that was found.
    refused = {
        # the "item" only goes on with the one before it
        "Signs may include a torn hat, due to strong wind or heavy rain.": "an item goes on with the item before it",
        "It is characterized by long walks, lasting days to weeks, and in some cases months.": (
            "an item goes on with the item before it"
        ),
        # ... or says more about it
        "Signs include a hat, often larger than a boat, a scarf, and gloves.": (
            "an item says more about the item before it"
        ),
        "Signs include a hat, a scarf, with ribbons, or gloves.": "an item begins with a preposition",
        # a whole clause: the lead-in stood in the subject, or the sentence is a row of clauses
        "Storms caused by wind may occur with rain, hail, or snow.": "an item holds a clause",
        "It drops due to rain, the wind is strong, and snow falls.": "an item holds a clause",
        # after "include" the verb has been said: a verb after the last item opens a new clause
        "Signs include a hat, a scarf, and a coat may show wear.": "an item holds a clause",
        "It is characterized by cold – failure to keep a hat, a scarf, or a glove.": "a remark after a dash",
        "It is caused by a gap, the space between the hat and the scarf.": (
            "the last 'and' or 'or' belongs to 'between', 'either' or 'both'"
        ),
        "It results from wind, either in the hills or elsewhere on the plain.": (
            "the last 'and' or 'or' belongs to 'between', 'either' or 'both'"
        ),
        "It is characterized by hats, scarves, and, less commonly, gloves and coats.": "an item is only a joining word",
        "Things such as hats, scarves, and gloves (e.g.": "a bracket is not closed",
        # words that describe, sharing the noun of the last item
        "Signs include a red, warm, and soft hat.": "the items share one noun",
        "It results from a mix of genetic, environmental, and social factors.": "the items share one noun",
        "The aims are to lessen signs such as cold and wet, to prevent harm, and to keep warm.": (
            "an item begins like a clause"
        ),
        # "be" in a clause that only leads up to the main one is no lead-in
        "Although few hats and treatments have shown to be helpful to wear, some scarves show promise, warmth, and style.": (
            "no lead-in"
        ),
    }
    for text, reason in refused.items():
        assert _items(text) == ([], reason), text


def test_what_looks_alike_and_is_a_list_stays_one():
    kept = {
        "Signs include a hat, a scarf, and occasionally gloves.": ["a hat", "a scarf", "occasionally gloves"],
        "Signs include a hat, a scarf, or in rare cases gloves.": ["a hat", "a scarf", "in rare cases gloves"],
        # every item names a place: a list of places
        "It is found in places such as the wrists, between fingers, or along the waistline.": [
            "the wrists",
            "between fingers",
            "along the waistline",
        ],
        "Signs include a hat, a scarf that is red, and gloves.": ["a hat", "a scarf that is red", "gloves"],
        "It can be many colours, including brown, red, and gray.": ["brown", "red", "gray"],
        "If it gets worse the symptoms are a hat, a scarf, and gloves.": ["a hat", "a scarf", "gloves"],
        # the first lead-in is taken: "due to" stands inside an item
        "Signs may include a tall hat, a round red face due to cold air, a scarf, and gloves.": [
            "a tall hat",
            "a round red face due to cold air",
            "a scarf",
            "gloves",
        ],
        # ... unless an item holds a lead-in that opens a list of its own
        "Signs include a hat, fluids such as water, juice, and broth.": ["water", "juice", "broth"],
    }
    for text, items in kept.items():
        assert _items(text) == (items, ""), text


def test_the_last_item_ends_where_the_sentence_goes_on():
    # The list is the subject: the verb after it belongs to the sentence, not to the last item.
    shortened = {
        "Things such as hats, scarves, and gloves may appear.": ["hats", "scarves", "gloves"],
        "Things such as hats, scarves, and warm gloves play a role.": ["hats", "scarves", "warm gloves"],
        "A plan, which includes hats, scarves and gloves has been made.": ["hats", "scarves", "gloves"],
        # a remark after a dash is not part of the last item
        "These include hats, scarves, and gloves—the warmest of all.": ["hats", "scarves", "gloves"],
    }
    for text, items in shortened.items():
        assert _items(text) == (items, ""), text
    text = "Things such as hats, scarves, and gloves may appear."
    claims, _reasons = split(text)
    assert [(claim.kind, claim.text) for claim in claims] == [
        (SENTENCE, text),
        (LIST_ITEM, "hats"),
        (LIST_ITEM, "scarves"),
        (LIST_ITEM, "gloves"),
    ]
    assert all(text[claim.start : claim.end] == claim.text for claim in claims)


def test_more_sentence_ends_after_a_single_letter_and_more_initials():
    # M2.6b: a label after any common word, the word "no", and an initial after "and" or beside another initial.
    for sample in (
        "They chose plan B. Then they left.",
        "They chose plan B. Aquatic birds agreed.",
        "The answer was no. Then they left.",
    ):
        assert len(sentences(sample)) == 2, sample
    for sample in (
        "It was found by Smith and J. Example in May.",
        "It was J. K. Example who came.",
        "He met John F. Example there.",
        "It ranks No. 4 in the list.",
    ):
        assert len(sentences(sample)) == 1, sample


def test_a_preposition_after_the_lead_in_does_not_belong_to_the_first_item():
    # M2.6c: "such as from A, B and C" lists A, B and C.
    assert _items("It spreads from a place such as from hills, valleys, lakes and woods.") == (
        ["hills", "valleys", "lakes", "woods"],
        "",
    )
    # Places that all go on with the first item are not items of a list.
    assert _items("Signs include fat pads along the collar, on the neck, and on the face.") == (
        [],
        "the other items go on with the first item",
    )
    # After "feeling tired", a describing word goes on with "feeling", not with the noun of the last item.
    assert _items("Signs are often vague such as feeling tired, weak, short of breath, or having less strength.") == (
        ["feeling tired", "weak", "short of breath", "having less strength"],
        "",
    )


def test_a_text_cut_off_by_its_source_is_marked_and_its_cut_item_is_not_kept():
    # M2.6c: one source cuts its texts at a fixed number of words. Such a text has exactly that many words and no
    # full stop; its last sentence is not whole, and the last item of a list in it is a fragment.
    tail = "Signs include a hat, a scarf, gloves, and a family"
    lead = " ".join(["Word"] * (CUT_OFF_WORDS - len(tail.split()))) + "."
    cut = f"{lead} {tail}"
    assert len(cut.split()) == CUT_OFF_WORDS
    claims, _reasons = split(cut)
    last = [claim for claim in claims if claim.kind == SENTENCE][-1]
    assert last.text == tail and last.cues == {"cut_off": [f"{CUT_OFF_WORDS} words"]}
    items = [claim for claim in claims if claim.kind == LIST_ITEM]
    assert [claim.text for claim in items] == ["a hat", "a scarf", "gloves"]
    assert all(claim.cues == last.cues and claim.parent == (last.start, last.end) for claim in items)
    # Only the last sentence is marked.
    assert [claim.cues for claim in claims if claim.kind == SENTENCE][0] == {}
    # The same words with a full stop, and a shorter text without one, are whole.
    for whole in (cut + ".", tail):
        claims, _reasons = split(whole)
        assert [claim.text for claim in claims if claim.kind == LIST_ITEM] == ["a hat", "a scarf", "gloves", "a family"]
        assert all("cut_off" not in claim.cues for claim in claims)


def test_a_list_whose_first_item_holds_a_preposition_is_marked_for_the_reviewer():
    # M2.6c: "infection with A, B, or C" and "loss of X, Y, and Z" have one wording and two meanings. The wording is
    # recorded on the items; nothing is decided.
    claims, _reasons = split("It is caused by infection with moths, beetles, or ants.")
    assert [(claim.text, claim.cues) for claim in claims] == [
        ("It is caused by infection with moths, beetles, or ants.", {}),
        ("infection with moths", {"first_item_preposition": ["with"]}),
        ("beetles", {"first_item_preposition": ["with"]}),
        ("ants", {"first_item_preposition": ["with"]}),
    ]
    claims, _reasons = split("Signs may include a hat (as in winter), a scarf, and gloves.")
    assert {repr(claim.cues) for claim in claims} == {"{'hedge': ['may']}"}
