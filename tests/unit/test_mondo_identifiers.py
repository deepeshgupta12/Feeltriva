"""The SNOMED CT and ICD-11 identifiers MONDO lists, their grades, and what WHO is asked (M2.16).

An invented vocabulary file and a stand-in for the WHO ICD API: no test here touches the network."""

from __future__ import annotations

import urllib.parse

import pytest
from feeltriva_ingestion.archives import ArchiveError
from feeltriva_ingestion.mondo_identifiers import (
    ICD_FOUNDATION,
    LINKED,
    NONE_LISTED,
    NOT_EQUIVALENT,
    SEVERAL,
    SNOMED,
    Identifier,
    grade,
    read_identifiers,
    resolve_icd,
)
from feeltriva_ingestion.vocabulary import IcdClient, IcdSettings

from tests.ontology_fixtures import ENTITY, FakeWho, entry, write_mondo

SETTINGS = IcdSettings(_env_file=None, icd_api_client_id="id-1", icd_api_client_secret="s3cret")  # noqa: S106 - a test value


def test_identifiers_are_read_with_the_marks_mondo_gives_them_and_everything_is_counted(tmp_path):
    registered = entry(write_mondo(tmp_path / "mondo.owl"), "mondo_release")
    version, identifiers, counted = read_identifiers(tmp_path, registered)
    assert version == "2026-01-01"
    # Only SNOMED CT and ICD-11 identifiers are read; the obsolete term and other vocabularies are left out.
    assert set(identifiers) == {"MONDO:9000001", "MONDO:9000002", "MONDO:9000003", "MONDO:9000006"}
    assert identifiers["MONDO:9000001"] == (
        Identifier(SNOMED, "111", ("MONDO:equivalentTo",)),  # the mark of another source ("DOID:1") is not a grade
        Identifier(SNOMED, "112", ("MONDO:relatedTo",)),
        Identifier(ICD_FOUNDATION, "900001", ("MONDO:equivalentTo",)),
    )
    assert counted == {
        "terms_with_an_identifier": 4,
        SNOMED: {
            "identifiers": 6,
            "marked_equivalent": 4,
            "other_marks": {"MONDO:relatedTo": 1, "MONDO:equivalentObsolete": 1},
        },
        ICD_FOUNDATION: {
            "identifiers": 3,
            "marked_equivalent": 2,
            "other_marks": {"MONDO:mondoIsBroaderThanSource": 1},
        },
    }
    with pytest.raises(ArchiveError, match="SHA-256"):
        read_identifiers(tmp_path, {**registered, "sha256": "0" * 64})
    with pytest.raises(ArchiveError, match="registered is 2025-12-31"):
        read_identifiers(tmp_path, {**registered, "version": "2025-12-31"})
    with pytest.raises(ArchiveError, match="missing"):
        read_identifiers(tmp_path, {**registered, "name": "absent.owl"})


def test_only_the_one_identifier_marked_equivalent_may_become_a_link(tmp_path):
    _version, identifiers, _counted = read_identifiers(
        tmp_path, entry(write_mondo(tmp_path / "mondo.owl"), "mondo_release")
    )
    outcome, chosen, of = grade(identifiers["MONDO:9000001"], SNOMED)
    assert (outcome, chosen.number, [found.number for found in of]) == (LINKED, "111", ["111", "112"])
    assert grade(identifiers["MONDO:9000001"], ICD_FOUNDATION)[:2] == (
        LINKED,
        Identifier(ICD_FOUNDATION, "900001", ("MONDO:equivalentTo",)),
    )
    # Two identifiers both marked equivalent: none is chosen.
    assert grade(identifiers["MONDO:9000003"], SNOMED)[:2] == (SEVERAL, None)
    # A broader identifier, and one equivalent to an obsolete concept, are not equivalents.
    assert grade(identifiers["MONDO:9000003"], ICD_FOUNDATION)[:2] == (NOT_EQUIVALENT, None)
    assert grade(identifiers["MONDO:9000006"], SNOMED)[:2] == (NOT_EQUIVALENT, None)
    assert grade((), SNOMED) == (NONE_LISTED, None, ())
    assert grade(identifiers["MONDO:9000002"], ICD_FOUNDATION) == (NONE_LISTED, None, ())
    assert not Identifier(SNOMED, "1", ("MONDO:equivalentTo", "MONDO:obsoleteEquivalent")).equivalent
    assert not Identifier(SNOMED, "1", ()).equivalent


def test_who_is_asked_for_the_official_title_and_where_the_entity_is_coded(tmp_path):
    api = FakeWho(
        {
            "900001": ("Synthetic fever disease", ("XZ01", "Synthetic fever disease", "900001")),
            "900006": ("Synthetic fever disease of the young", ("XZ01", "Synthetic fever disease", "900001")),
            "900009": ("Synthetic grouping", None),
        }
    )
    client = IcdClient(SETTINGS, tmp_path / "cache", api, pause=0, online=True)
    same = resolve_icd(client, "2026-01", "900001")
    assert same == {
        "title": "Synthetic fever disease",
        "uri": ENTITY + "900001",
        "mms": {
            "code": "XZ01",
            "title": "Synthetic fever disease",
            "uri": "http://id.who.int/icd/release/11/2026-01/mms/900001",
            "same_entity": True,
        },
    }
    # WHO codes this entity under another, broader one: its own title is kept and the MMS entity is not "the same".
    broader = resolve_icd(client, "2026-01", "900006")
    assert (broader["title"], broader["mms"]["code"], broader["mms"]["same_entity"]) == (
        "Synthetic fever disease of the young",
        "XZ01",
        False,
    )
    assert resolve_icd(client, "2026-01", "900009") == {
        "title": "Synthetic grouping",
        "uri": ENTITY + "900009",
        "mms": None,
    }
    assert resolve_icd(client, "2026-01", "999999") is None  # WHO has no such entity
    # Only identifiers leave the machine, and an answer already received is not asked for again.
    assert all(
        url.startswith("https://id.who.int/icd/") and "synthetic" not in urllib.parse.unquote(url).lower()
        for url in api.seen
    )
    asked = len(api.seen)
    assert resolve_icd(client, "2026-01", "900001") == same and len(api.seen) == asked
