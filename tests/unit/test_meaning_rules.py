"""Rules that propose a feature's kind and the meaning of a zero (M2.7). No database, no files."""

from __future__ import annotations

from collections import Counter

import pytest
from feeltriva_ingestion.meanings import (
    UNDECIDED,
    WORDING_RULES,
    ZERO_NO_ANSWER,
    ZERO_NOT_RECORDED,
    ZERO_UNKNOWN,
    classify_kind,
    classify_zero,
    is_cut_off,
    propose_age_unit,
    readable,
)
from feeltriva_ingestion.meanings_load import same_cases

SYMPTOMS = frozenset({"fever", "cough", "chest pain"})


def kind(heading: str, source: str = "") -> tuple[str, str]:
    proposal = classify_kind(heading, source, SYMPTOMS)
    return proposal.kind, proposal.rule


def test_headings_are_read_as_plain_words():
    assert readable("E_91_do_you_have_a_fever") == "do you have a fever"
    assert readable("sharp_chest_pain") == "sharp chest pain"
    assert readable("e 204 have you traveled out of") == "have you traveled out of"


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        # The handoff: "Do not treat a history question as an active symptom."
        ("E_105_have_you_ever_had_a", ("history", "past_event")),
        ("E_118_have_you_ever_had_pneumonia", ("history", "past_event")),
        ("E_19_have_you_been_diagnosed_with", ("history", "past_event")),
        ("E_137_have_you_ever_had_surgery", ("history", "past_event")),
        ("E_142_does_your_mother_suffer_from", ("history", "relatives")),
        ("E_25_have_any_of_your_family", ("history", "relatives")),
        ("E_106_do_you_have_heart_failure", ("history", "known_condition")),
        ("E_12_do_you_have_a_known", ("history", "known_condition")),
        ("E_81_do_you_suffer_from_chronic", ("history", "known_condition")),
        ("E_44_do_you_take_corticosteroids", ("history", "treatment")),
        ("E_1_are_you_currently_being_treated", ("history", "treatment")),
        ("E_79_do_you_smoke_cigarettes", ("risk_factor", "exposure_or_lifestyle")),
        ("E_191_are_you_a_former_smoker", ("risk_factor", "exposure_or_lifestyle")),
        ("E_204_have_you_traveled_out_of", ("risk_factor", "exposure_or_lifestyle")),
        ("E_143_do_you_exercise_regularly_4", ("risk_factor", "exposure_or_lifestyle")),
        ("E_208_is_your_bmi_less_than", ("measurement", "body_measure")),
        # Symptoms: a description, something felt or noticed, or a symptom another source names.
        ("E_130_what_color_is_the_rash", ("symptom", "description_of_a_symptom")),
        ("E_57_does_the_pain_radiate_to", ("symptom", "about_a_named_symptom")),
        ("E_16_do_you_feel_anxious", ("symptom", "present_experience")),
        ("E_66_are_you_experiencing_shortness_of", ("symptom", "present_experience")),
        ("E_91_do_you_have_a_fever", ("symptom", "names_a_symptom")),
        ("E_14_do_you_have_chest_pain", ("symptom", "names_a_symptom")),
        # "Do you have ..." also introduces diagnoses, so on its own it settles nothing.
        ("E_121_do_you_have_a_deviated", (UNDECIDED, "none")),
        ("E_188_do_you_have_pale_stools", (UNDECIDED, "none")),
        ("E_0_have_you_recently_had_a", (UNDECIDED, "none")),
        ("E_23_do_you_ever_temporarily_stop", (UNDECIDED, "none")),  # "do you ever" is not the past
    ],
)
def test_question_wording_decides_the_kind(heading, expected):
    assert kind(heading) == expected


def test_a_question_cut_off_in_the_source_is_reported_as_such():
    assert is_cut_off("E_0_have_you_recently_had_a") and not is_cut_off("E_188_do_you_have_pale_stools")
    assert not is_cut_off("sharp_chest_pain")  # a column name, not a question
    assert "cut off in the source file" in classify_kind("E_0_have_you_recently_had_a", "", SYMPTOMS).reason_undecided
    assert (
        classify_kind("E_188_do_you_have_pale_stools", "", SYMPTOMS).reason_undecided
        == "no rule recognises the wording"
    )


def test_a_term_is_a_symptom_only_when_its_source_says_so():
    assert kind("sharp chest pain", "file name `symptoms.csv`") == ("symptom", "stated_by_source")
    assert kind("sharp chest pain") == (UNDECIDED, "none")
    assert kind("exercise dyspnea", "column prefix `symptom_`") == ("symptom", "stated_by_source")  # not a habit


def test_wording_overrides_a_source_that_calls_everything_a_symptom():
    for term, expected in (
        ("family history", "history"),
        ("history of alcohol consumption", "risk_factor"),
        ("abusing alcohol", "risk_factor"),
        ("receiving blood transfusion", "risk_factor"),
    ):
        proposal = classify_kind(term, "file name `diseases_symptoms.csv`", SYMPTOMS)
        assert proposal.kind == expected
        assert "the source presents it as a symptom" in proposal.basis and "the wording decides" in proposal.basis


def test_no_rule_before_the_symptom_rules_proposes_a_symptom_and_none_proposes_a_sign():
    kinds = [rule.kind for rule in WORDING_RULES]
    first_symptom = kinds.index("symptom")
    assert "symptom" not in kinds[:first_symptom] and set(kinds[first_symptom:]) == {"symptom"}
    assert "sign" not in kinds and all(rule.basis for rule in WORDING_RULES)


def zero(**given) -> tuple[str, str]:
    defaults = {
        "is_list_term": False,
        "always_affirmed": False,
        "identical_group": (),
        "describes_a_symptom": False,
        "same_cases_as_lists": "",
    }
    proposal = classify_zero(**{**defaults, **given})
    assert proposal.basis
    return proposal.zero, proposal.rule


def test_a_zero_is_never_proposed_to_be_a_denial():
    assert zero() == (ZERO_UNKNOWN, "no_evidence")
    assert zero(is_list_term=True) == (ZERO_NOT_RECORDED, "list_term")
    assert zero(same_cases_as_lists="lists.csv") == (ZERO_NOT_RECORDED, "same_cases_as_lists")
    assert zero(always_affirmed=True) == (ZERO_NO_ANSWER, "affirmed_in_every_row")
    assert zero(identical_group=("E_55", "E_56")) == (ZERO_NO_ANSWER, "recorded_together")
    assert zero(describes_a_symptom=True) == (ZERO_NO_ANSWER, "description_question")
    # A column that is not a yes/no answer stays that, whatever else is known about the file.
    assert zero(always_affirmed=True, same_cases_as_lists="lists.csv")[0] == ZERO_NO_ANSWER
    every = [
        zero(is_list_term=a, always_affirmed=b, identical_group=c, describes_a_symptom=d, same_cases_as_lists=e)[0]
        for a in (False, True)
        for b in (False, True)
        for c in ((), ("x",))
        for d in (False, True)
        for e in ("", "lists.csv")
    ]
    assert set(every) == {ZERO_UNKNOWN, ZERO_NOT_RECORDED, ZERO_NO_ANSWER} and "absent" not in every


def test_age_unit_is_proposed_only_when_the_range_singles_it_out():
    assert propose_age_unit(0, 109, True)[0] == "years" and propose_age_unit(1, 90, True)[0] == "years"
    assert "No source documentation states the unit" in propose_age_unit(1, 90, True)[1]
    assert propose_age_unit(0, 36, True)[0] == UNDECIDED  # could be months
    assert propose_age_unit(0.5, 80.5, False)[0] == UNDECIDED
    assert propose_age_unit(-1, 90, True)[0] == UNDECIDED and propose_age_unit(0, 900, True)[0] == UNDECIDED


def _scan(cases: list[tuple[str, frozenset[str]]]) -> dict:
    return {"bags": Counter(hash(case) for case in cases), "label_rows": Counter(label for label, _ in cases)}


def test_two_files_hold_the_same_cases_only_when_every_case_matches():
    listed = [("flu", frozenset({"fever"})), ("flu", frozenset({"fever", "cough"})), ("cold", frozenset({"cough"}))]
    extra = [("asthma", frozenset({"wheeze"}))]  # the matrix may hold labels the list file does not have
    assert same_cases(_scan(listed + extra), _scan(listed)) == {"labels": 2, "rows": 3}
    assert same_cases(_scan(listed[:2] + extra), _scan(listed)) is None  # a case is missing
    changed = [listed[0], ("flu", frozenset({"fever"})), listed[2]]
    assert same_cases(_scan(changed), _scan(listed)) is None  # same number of rows, different symptoms
    assert same_cases(_scan(listed + [listed[0]]), _scan(listed)) is None  # one more row under a shared label
    assert same_cases(_scan(listed), _scan([])) is None


# -- a source that documents its own questions (M2.12) ------------------------------------------------


def _entry(question, antecedent, answer_type="yes_no", default=0, values=None):
    return {
        "question": question,
        "is_antecedent": antecedent,
        "answer_type": answer_type,
        "default_value": default,
        "values": values or {},
    }


def test_the_sources_own_flag_decides_symptom_or_not():
    from feeltriva_ingestion.meanings import classify_kind_with_dictionary as classify

    symptom = classify(_entry("Do you have a fever (either felt or measured with a thermometer)?", False))
    assert (symptom.kind, symptom.rule) == ("symptom", "source_dictionary") and "Do you have a fever" in symptom.basis
    # "Do you have ..." questions that the wording alone could not settle (M2.7) are settled by the source.
    for question, kind, rule in (
        ("Do you have a problem with poor circulation?", "history", "source_dictionary"),
        ("Have you recently had a viral infection?", "history", "source_dictionary"),
        ("Have you ever had a heart attack?", "history", "source_dictionary+past_event"),
        (
            "Do you have high blood pressure or do you take medications to treat it?",
            "history",
            "source_dictionary+treatment",
        ),
        ("Do you smoke cigarettes?", "risk_factor", "source_dictionary+exposure_or_lifestyle"),
        (
            "Have you traveled out of the country in the last 4 weeks?",
            "risk_factor",
            "source_dictionary+exposure_or_lifestyle",
        ),
        ("Is your BMI less than 18.5, or are you underweight?", "measurement", "source_dictionary+body_measure"),
    ):
        proposal = classify(_entry(question, True))
        assert (proposal.kind, proposal.rule) == (kind, rule), question
        assert "antecedent" in proposal.basis
    # An antecedent is never a symptom, even when its wording sounds like one.
    assert classify(_entry("Do you feel anxious?", True)).kind == "history"


def test_a_documented_zero_is_the_sources_no_but_still_not_an_approved_denial():
    from feeltriva_ingestion.meanings import ZERO_NO_PER_SOURCE
    from feeltriva_ingestion.meanings import classify_zero_with_dictionary as classify

    yes_no = classify(_entry("Do you have a fever?", False))
    assert (yes_no.zero, yes_no.rule) == (ZERO_NO_PER_SOURCE, "source_dictionary_default") and yes_no.zero != "absent"
    several = classify(
        _entry("Characterize your pain:", False, "several_of_several", "V_11", {"V_11": "NA", "V_20": "sharp"})
    )
    assert (several.zero, several.rule) == (ZERO_NO_ANSWER, "source_dictionary_answer_type")
    assert "2 possible answers" in several.basis and "'V_11'" in several.basis


def test_rows_are_traced_to_the_release_as_runs_in_file_order():
    from feeltriva_ingestion.release import _answered, heading_is_start_of, trace

    release = {"train": [10, 11, 12, 13, 14], "validate": [20, 21], "test": [30]}
    traced = trace([10, 11, 13, 14, 20, 21], release)  # train rows 1-2, a gap, train rows 4-5, then all of validate
    assert (traced["rows"], traced["traced"], traced["not_in_release"]) == (6, 6, 0)
    assert [(r["our_first_row"], r["release_split"], r["release_first_row"], r["rows"]) for r in traced["runs"]] == [
        (1, "train", 1, 2),
        (3, "train", 4, 2),
        (5, "validate", 1, 2),
    ]
    assert trace([10, 99, 11], release)["not_in_release"] == 1  # a row the release does not contain
    assert trace([12, 12], {"train": [12, 5, 12, 12]})["runs"][0]["release_first_row"] == 3  # the longest run wins
    assert _answered("['E_48', 'E_54_@_V_161', 'E_54_@_V_183', 'E_56_@_4']") == {"E_48", "E_54", "E_56"}
    assert _answered("[]") == frozenset()
    assert heading_is_start_of(
        "E_174_have_you_been_unintentionally_losin", "Have you been unintentionally losing weight?"
    )
    assert heading_is_start_of(
        "E_47_do_you_suffer_from_crohns", "Do you suffer from Crohn's disease or ulcerative colitis?"
    )
    assert heading_is_start_of("E_187_did_you_eat_darkfleshed_fish", "Did you eat dark-fleshed fish (such as tuna)?")
    assert not heading_is_start_of("E_91_do_you_have_a_fever", "Do you have a cough?")
    assert not heading_is_start_of("fever", "Do you have a fever?")
