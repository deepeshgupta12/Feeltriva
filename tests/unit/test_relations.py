"""Suggested synonyms and subtypes from wording (M2.8). No database."""

from __future__ import annotations

from feeltriva_ingestion.relations import SUBTYPE, SYNONYM, content_words, spelling_key, suggest, suggestion_id


def subjects(*labels: str) -> list[dict]:
    return [{"id": f"id{n}", "label": label, "shown": label} for n, label in enumerate(labels)]


def pairs(found: list[dict]) -> set[tuple[str, str, str, str]]:
    return {(f["relation"], f["left_label"], f["right_label"], f["signals"][0]["signal"]) for f in found}


def test_labels_are_compared_as_words_without_order_number_or_filler():
    assert content_words("Pain in the Back") == content_words("back_pains") == frozenset({"pain", "back"})
    assert content_words("loss of consciousness") == frozenset({"loss", "consciousness"})  # "ss" is not a plural
    assert content_words("ebola virus disease") == frozenset(
        {"ebola", "virus", "disease"}
    ) and "arthritis" in content_words("arthritis")
    assert spelling_key("Diarrhoea") == spelling_key("diarrhea") and spelling_key("anaemia") == spelling_key("anemia")
    assert spelling_key("does") == "does"  # short words are left alone


def test_possible_synonyms_are_found_with_the_closest_likeness_as_the_reason():
    found = suggest(
        subjects(
            "skin_rash",
            "skin rash",
            "pain in back",
            "back pain",
            "headaches",
            "headache",
            "diarrhoea",
            "diarrhea",
            "cough",
        ),
        {},
    )
    assert pairs(found) == {
        (SYNONYM, "skin_rash", "skin rash", "same_words_other_punctuation"),
        (SYNONYM, "pain in back", "back pain", "same_words_other_order_or_number"),
        (SYNONYM, "headaches", "headache", "same_words_other_order_or_number"),
        (SYNONYM, "diarrhoea", "diarrhea", "british_or_american_spelling"),
    }
    assert all(len(f["signals"]) == 1 for f in found)  # one reason per pair when wording alone explains it


def test_an_added_word_makes_a_possible_subtype_never_a_synonym():
    found = suggest(
        subjects(
            "bronchitis",
            "acute bronchitis",
            "chronic bronchitis",
            "type 2 diabetes",
            "diabetes",
            "severe acute chest pain",
            "pain",
        ),
        {},
    )
    assert pairs(found) == {
        (SUBTYPE, "acute bronchitis", "bronchitis", "adds_words"),
        (SUBTYPE, "chronic bronchitis", "bronchitis", "adds_words"),
        (SUBTYPE, "type 2 diabetes", "diabetes", "adds_words"),
    }  # acute and chronic are not suggested as the same; three added words is too far to suggest
    by = {f["left_label"]: f for f in found}
    assert by["acute bronchitis"]["signals"] == [{"signal": "adds_words", "words": ["acute"]}]
    assert by["type 2 diabetes"]["signals"][0]["words"] == ["2", "type"]


def test_two_candidates_with_the_same_standard_code_are_possible_synonyms():
    listed = subjects("heart attack", "myocardial infarction", "flu")
    codes = {
        "id0": {("ICD-11 MMS", "2026-01", "BA41")},
        "id1": {("ICD-11 MMS", "2026-01", "BA41")},
        "id2": {("ICD-11 MMS", "2026-01", "1E32")},
    }
    found = suggest(listed, codes)
    assert len(found) == 1 and found[0]["relation"] == SYNONYM
    assert found[0]["signals"] == [
        {"signal": "same_standard_code", "vocabulary": "ICD-11 MMS", "release": "2026-01", "code": "BA41"}
    ]
    both = suggest(
        subjects("skin_rash", "skin rash"),
        {"id0": {("ICD-11 MMS", "2026-01", "ME66")}, "id1": {("ICD-11 MMS", "2026-01", "ME66")}},
    )
    assert [s["signal"] for s in both[0]["signals"]] == [
        "same_standard_code",
        "same_words_other_punctuation",
    ]  # both reasons kept


def test_a_pair_has_one_identity_whichever_way_round_it_is_found():
    assert suggestion_id("disease", SYNONYM, "a", "b") == suggestion_id("disease", SYNONYM, "b", "a")
    assert suggestion_id("disease", SUBTYPE, "a", "b") != suggestion_id(
        "disease", SUBTYPE, "b", "a"
    )  # narrower, broader
    assert suggestion_id("disease", SYNONYM, "a", "b") != suggestion_id("feature", SYNONYM, "a", "b")
    assert suggest(subjects("cough", "fever"), {}) == []
