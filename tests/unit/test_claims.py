"""Splitting a statement into single claims with exact spans (M2.6): the rules. Invented sentences; no database."""

from __future__ import annotations

from feeltriva_ingestion.claims import LIST_ITEM, SENTENCE, VERSION, cues, item_name, list_items, sentences, split


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
    # The list starts at the last lead-in that still leaves three items: here the second part of the sentence.
    assert _items("Some can be taken by mouth, and these include alpha, beta, gamma and delta.")[0] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
    ]
    # ... and at the earlier one when the later would leave too few.
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
