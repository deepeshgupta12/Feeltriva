"""Reading HPO and MONDO and the rule for a link (M2.14). Invented vocabulary files only; no database."""

from __future__ import annotations

import pytest
from feeltriva_ingestion.archives import ArchiveError
from feeltriva_ingestion.ontologies import (
    ABBREVIATION_ONLY,
    HPO,
    LINKED,
    LOOSER_ONLY,
    MONDO,
    NEAREST,
    NOT_LINKABLE,
    NOTHING,
    SEVERAL,
    lookup,
    read_hpo,
    read_mondo,
    read_vocabulary,
)

from tests.ontology_fixtures import entry, write_hpo, write_mondo


@pytest.fixture
def hpo(tmp_path):
    return read_hpo(write_hpo(tmp_path / "hp.json"))


@pytest.fixture
def mondo(tmp_path):
    return read_mondo(write_mondo(tmp_path / "mondo.owl"))


def test_every_entry_of_an_hpo_file_is_counted_and_placed_in_a_branch(hpo):
    assert (hpo.system, hpo.version) == (HPO, "2026-01-01")
    counted = hpo.inventory
    assert (counted["entries_in_file"], counted["terms"], counted["entries_of_other_vocabularies"]) == (14, 13, 1)
    assert (counted["current"], counted["obsolete"]) == (12, 1) and sum(counted["by_branch"].values()) == 12
    assert counted["by_branch"] == {"root": 1, "Phenotypic abnormality": 8, "Mode of inheritance": 1, "Frequency": 2}
    assert (counted["exact_synonyms"], counted["looser_synonyms"], counted["synonyms_that_are_not_names"]) == (6, 1, 1)
    assert counted["parent_links"] == 11 and hpo.branch["HP:9000003"] == "obsolete"
    # A term two steps below a branch root still belongs to it; frequency, inheritance, the root and
    # the obsolete term may not be linked.
    assert hpo.branch["HP:9000002"] == "Phenotypic abnormality" and "HP:9000002" in hpo.linkable
    assert not {"HP:0000001", "HP:0040279", "HP:9000004", "HP:0000005", "HP:9000003"} & hpo.linkable
    assert counted["linkable"] == len(hpo.linkable) == 8
    kinds = {name.text: (name.how, name.kind) for name in hpo.terms["HP:9000001"].synonyms}
    assert kinds == {
        "Shining skin": ("exact_synonym", "layperson"),
        "SG": ("exact_synonym", "abbreviation"),
        "Brightness": ("related_synonym", ""),
    }


def test_a_mondo_file_is_read_with_its_branches_and_the_types_of_its_synonyms(mondo):
    assert (mondo.system, mondo.version) == (MONDO, "2026-01-01")
    counted = mondo.inventory
    assert (counted["entries_in_file"], counted["terms"], counted["entries_of_other_vocabularies"]) == (13, 12, 1)
    assert (counted["current"], counted["obsolete"]) == (11, 1) and sum(counted["by_branch"].values()) == 11
    assert counted["by_branch"] == {
        "human disease": 3,
        "non-human animal disease": 2,
        "injury": 2,
        "disease susceptibility": 2,
        "disease characteristic": 1,
        "disease, no narrower branch": 1,
    }
    # Human diseases and injuries may be linked; animal diseases, a susceptibility and an obsolete term may not.
    assert mondo.linkable == {"MONDO:0700096", "MONDO:9000001", "MONDO:9000006", "MONDO:0021178", "MONDO:9000003"}
    # A parent given as a restriction is not a parent: the human term does not become an animal disease.
    assert mondo.terms["MONDO:9000001"].parents == ("MONDO:0700096",)
    kinds = {name.text: (name.how, name.kind) for name in mondo.terms["MONDO:9000001"].synonyms}
    assert kinds == {
        "pretend fever": ("exact_synonym", ""),
        "SFD": ("exact_synonym", "abbreviation"),
        "synthetic foever disease": ("exact_synonym", "uk spelling synonym"),
        "mild pretend fever": ("narrow_synonym", ""),
    }


def test_a_name_is_linked_only_to_a_term_that_carries_exactly_that_name(hpo, mondo):
    by_label = lookup(hpo, "synthetic_glow")
    assert (by_label.outcome, by_label.link.code, by_label.link.how, by_label.link.branch) == (
        LINKED,
        "HP:9000001",
        "label",
        "Phenotypic abnormality",
    )
    assert by_label.link.uri == "http://purl.obolibrary.org/obo/HP_9000001" and by_label.link.title == "Synthetic glow"
    # The source's naming word "symptom" is dropped; the kind of synonym the vocabulary states is kept.
    by_synonym = lookup(hpo, "Shining-Skin symptom")
    assert (by_synonym.link.code, by_synonym.link.how, by_synonym.link.kind, by_synonym.link.matched) == (
        "HP:9000001",
        "exact_synonym",
        "layperson",
        "Shining skin",
    )
    spelling = lookup(mondo, "synthetic foever disease")
    assert (spelling.link.code, spelling.link.kind) == ("MONDO:9000001", "uk spelling synonym")
    assert lookup(mondo, "synthetic cut").link.branch == "injury"
    # The animal disease with the same synonym is left out, so one term remains and is linked.
    assert lookup(mondo, "pretend fever").link.code == "MONDO:9000001"


def test_an_abbreviation_a_looser_synonym_and_a_term_that_may_not_be_linked_give_no_link(hpo, mondo):
    for vocabulary, name, code in ((hpo, "sg", "HP:9000001"), (mondo, "SFD", "MONDO:9000001")):
        found = lookup(vocabulary, name)
        assert (found.outcome, found.link) == (ABBREVIATION_ONLY, None) and "abbreviation" in found.reason
        assert [(c.code, c.kind) for c in found.candidates] == [(code, "abbreviation")]
    for vocabulary, name, how in (
        (hpo, "brightness", "related_synonym"),
        (mondo, "mild pretend fever", "narrow_synonym"),
    ):
        found = lookup(vocabulary, name)
        assert (found.outcome, found.link) == (LOOSER_ONLY, None) and [c.how for c in found.candidates] == [how]
    for vocabulary, name, where in (
        (hpo, "synthetic fog", "obsolete"),
        (hpo, "very often", "Frequency"),
        (mondo, "synthetic ache", "obsolete"),
        (mondo, "synthetic leaning", "disease susceptibility"),
        (mondo, "synthetic fever disease, dog", "non-human animal disease"),
    ):
        found = lookup(vocabulary, name)
        assert (found.outcome, found.link) == (NOT_LINKABLE, None) and where in found.reason, name
        assert [c.branch for c in found.candidates] == [where]


def test_when_several_terms_carry_the_name_none_is_chosen_unless_one_has_it_as_its_label(hpo):
    several = lookup(hpo, "twin sign")
    assert (several.outcome, several.link) == (SEVERAL, None)
    assert [c.code for c in several.candidates] == ["HP:9000005", "HP:9000006"] and "2 terms" in several.reason
    label_wins = lookup(hpo, "twin mark")
    assert (label_wins.outcome, label_wins.link.code, label_wins.link.how) == (LINKED, "HP:9000007", "label")
    assert "HP:9000008" in label_wins.link.note  # the other term that lists the name is shown to the reviewer


def test_a_name_without_a_link_gets_a_reason_and_the_nearest_terms(hpo, mondo):
    near = lookup(hpo, "synthetic glow of the hand")
    assert (near.outcome, near.link) == (NEAREST, None) and near.reason
    # Nearest first: three of four words in common, then two of three. Never the abbreviation.
    assert [(c.code, c.note[:4]) for c in near.candidates] == [("HP:9000009", "0.75"), ("HP:9000001", "0.67")]
    assert all(c.kind != "abbreviation" for c in near.candidates)
    nothing = lookup(hpo, "unheard thing")
    assert (nothing.outcome, nothing.link, nothing.candidates) == (NOTHING, None, ()) and nothing.reason
    # Nearest terms are taken from linkable terms only: the animal disease is never offered. Three of
    # four words in common comes before three of five.
    assert [(c.code, c.note[:4]) for c in lookup(mondo, "synthetic fever disease of the old").candidates] == [
        ("MONDO:9000001", "0.75"),
        ("MONDO:9000006", "0.60"),
    ]


def test_a_file_is_read_only_when_it_is_the_registered_one(tmp_path):
    path = write_hpo(tmp_path / "hp.json")
    registered = entry(path, "hpo_release")
    assert read_vocabulary(tmp_path, registered).version == "2026-01-01"
    with pytest.raises(ArchiveError, match="SHA-256"):
        read_vocabulary(tmp_path, {**registered, "sha256": "0" * 64})
    with pytest.raises(ArchiveError, match="registered is 2025-12-31"):
        read_vocabulary(tmp_path, {**registered, "version": "2025-12-31"})
    with pytest.raises(ArchiveError, match="missing"):
        read_vocabulary(tmp_path, {**registered, "name": "absent.json"})
    owl = write_mondo(tmp_path / "mondo.owl")
    assert read_vocabulary(tmp_path, entry(owl, "mondo_release")).system == MONDO


def test_a_file_whose_layout_changed_is_refused(tmp_path):
    with pytest.raises(ArchiveError, match="layout of the file has changed"):
        read_hpo(write_hpo(tmp_path / "hp.json", frequency_label="How often"))
    with pytest.raises(ArchiveError, match="layout of the file has changed"):
        read_mondo(write_mondo(tmp_path / "mondo.owl", human_label="disease of people"))
    broken = tmp_path / "broken.owl"
    broken.write_text("<rdf:RDF><owl:Class>", encoding="utf-8")
    with pytest.raises(ArchiveError, match="not a readable OWL file"):
        read_mondo(broken)
    not_hpo = tmp_path / "other.json"
    not_hpo.write_text('{"something": []}', encoding="utf-8")
    with pytest.raises(ArchiveError, match="not an HPO file"):
        read_hpo(not_hpo)
