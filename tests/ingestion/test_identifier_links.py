"""SNOMED CT and ICD-11 identifiers taken from MONDO, stored for review (M2.16).

An invented vocabulary file and a stand-in for the WHO ICD API: nothing leaves the machine."""

from __future__ import annotations

import csv
import os
import uuid

import pytest
from feeltriva_api.models import Disease, DiseaseMapping, MappingRelease, Source
from feeltriva_ingestion.archives import RAW_DIR
from feeltriva_ingestion.identifier_links import (
    DIFFERENT,
    ICD11,
    METHOD,
    REVIEW_FILE,
    SAME,
    SAME_CATEGORY,
    check,
    import_identifiers,
    summarise,
    write_review,
)
from feeltriva_ingestion.load import RELEASE_ID, source_id
from feeltriva_ingestion.mondo_identifiers import (
    ICD_FOUNDATION,
    LINKED,
    LINKED_FOUNDATION,
    NONE_LISTED,
    NOT_EQUIVALENT,
    SEVERAL,
    SNOMED,
    UNKNOWN_TO_WHO,
    read_identifiers,
)
from feeltriva_ingestion.release import load_supplementary
from feeltriva_ingestion.vocabulary import ICD, IcdClient, IcdSettings, link_id
from sqlalchemy import text

from tests.ontology_fixtures import FakeWho, entry, write_mondo

SETTINGS = IcdSettings(_env_file=None, icd_api_client_id="id-1", icd_api_client_secret="s3cret")  # noqa: S106 - a test value


def test_the_command_needs_a_registered_mondo_file():
    with pytest.raises(SystemExit, match="no MONDO file is registered"):
        import_identifiers(entries=[{"name": "hp.json", "kind": "hpo_release"}], database_url="postgresql://unused")


@pytest.mark.postgres
def test_identifiers_mondo_marks_equivalent_become_pending_links_one_row_per_label_and_code(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"ids-{tag}.zip", "data.csv")
    # label -> the MONDO term it is linked to (None: no MONDO link), and the review status of that link
    labels = {
        "fever": ("MONDO:9000001", "pending"),
        "cut": ("MONDO:9000003", "pending"),
        "young": ("MONDO:9000006", "pending"),
        "other": ("MONDO:9000001", "pending"),
        "grain": ("MONDO:9000001", "pending"),
        "unknown": ("MONDO:9000002", "pending"),  # a term for which MONDO lists a SNOMED CT identifier only
        "refused": ("MONDO:9000001", "rejected"),
        "bare": ("MONDO:0700096", "pending"),  # a term for which MONDO lists no identifier
        "unlinked": (None, ""),
    }
    ids = {key: f"dis_{tag}_{key}" for key in labels}
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"ids-{tag}.zip/data.csv", version="t", sha256="0"))
        for key in labels:
            tx.add(Disease(disease_id=ids[key], preferred_name=f"{key} {tag}"))
        tx.flush()
        for key in labels:
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{key}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    original_label=f"{key} {tag}",
                    disease_id=ids[key],
                    method="lexical_casefold_whitespace",
                )
            )
        tx.flush()
        for key, (code, status) in labels.items():
            if code:
                tx.execute(
                    text(
                        """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, uri,
                                                          match_method, status, reviewer)
                           VALUES (:l, :d, 'MONDO', '2026-01-01', :c, :t, 'u', 'exact_label', CAST(:s AS review_state), :r)"""
                    ),
                    {
                        "l": f"tl_{tag}_{key}",
                        "d": ids[key],
                        "c": code,
                        "t": f"mondo name of {key}",
                        "s": status,
                        "r": "dev-reviewer:test" if status == "rejected" else None,
                    },
                )
        # What the name search of M2.11 would have stored: the same ICD-11 code for "fever", another one for "other".
        # and, for "grain", only the unspecified sub-code of the same category, as the name search does for a bare name.
        mms = "http://id.who.int/icd/release/11/2026-01/mms/900001"
        for key, code, uri in (
            ("fever", "XZ01", "u"),
            ("other", "QQ99", "u"),
            ("grain", "XZ01.Z", f"{mms}/unspecified"),
        ):
            tx.execute(
                text(
                    """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, uri, match_method)
                       VALUES (:l, :d, 'ICD-11 MMS', '2026-01', :c, 'by name', :u, 'exact_title')"""
                ),
                {"l": link_id(ids[key], ICD, "2026-01", code), "d": ids[key], "c": code, "u": uri},
            )
    entries = [entry(write_mondo(tmp_path / "mondo.owl", tag=tag), "mondo_release")]
    api = FakeWho(
        {
            "900001": ("Synthetic fever disease", ("XZ01", "Synthetic fever disease", "900001")),
            "900006": ("Synthetic fever disease of the young", ("XZ01", "Synthetic fever disease", "900001")),
        }
    )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]

    def run():
        return import_identifiers(tmp_path, url, IcdClient(SETTINGS, tmp_path / "cache", api, pause=0), entries, [sid])

    result = run()
    assert check(result) == []
    assert (result["mondo_release"], result["icd_release"]) == ("2026-01-01", "2026-01")
    assert result["mondo_links"] == {"read": 8, "rejected_and_not_used": 1}
    by = {item["name"].split()[0]: item for item in result["items"]}
    # Not the rejected link, not the unlinked label.
    assert set(by) == {"fever", "cut", "young", "other", "grain", "unknown", "bare"}
    outcomes = {
        key: (item["outcomes"][SNOMED]["outcome"], item["outcomes"][ICD11]["outcome"]) for key, item in by.items()
    }
    assert outcomes == {
        "fever": (LINKED, LINKED),
        "cut": (SEVERAL, NOT_EQUIVALENT),
        "young": (NOT_EQUIVALENT, LINKED_FOUNDATION),
        "other": (LINKED, LINKED),
        "grain": (LINKED, LINKED),
        "unknown": (LINKED, NONE_LISTED),
        "bare": (NONE_LISTED, NONE_LISTED),
    }
    agreement = {key: by[key]["agreement"] for key in ("fever", "other", "grain", "young")}
    assert agreement == {"fever": SAME, "other": DIFFERENT, "grain": SAME_CATEGORY, "young": ""}
    # One row per label and code: the ICD-11 code the name search already stored for "fever" is not stored again.
    assert result["inserted"] == {SNOMED: 4, ICD: 2, ICD_FOUNDATION: 1}
    counts = summarise(result)
    assert counts["groups"] == {"disease labels": 7}
    assert counts["agreement"] == {SAME: 1, DIFFERENT: 1, SAME_CATEGORY: 1}
    assert counts["rows"][("disease labels", SNOMED, "several identifiers marked equivalent")] == 1

    with owner_db.transaction(None) as tx:
        found = tx.execute(
            text(
                """SELECT disease_id, system, code, system_version, title, uri, match_method, status::text, reviewer,
                          detail -> 'via' ->> 'code', detail ->> 'marks', detail -> 'also_through_mondo' ->> 'icd_code',
                          detail -> 'category_through_mondo' ->> 'icd_code', detail -> 'coded_in_mms_under' ->> 'code',
                          detail ? 'title_is'
                   FROM terminology_links WHERE disease_id LIKE :d AND system <> 'MONDO'"""
            ),
            {"d": f"dis_{tag}_%"},
        ).all()
    stored = {(row[0].rsplit("_", 1)[1], row[1], row[2]): tuple(row[3:]) for row in found}
    snomed_uri, mms_uri = "http://snomed.info/id/", "http://id.who.int/icd/release/11/2026-01/mms/900001"
    marks = '["MONDO:equivalentTo"]'

    def through_mondo(version, title, uri, term, **more):
        return (
            version,
            title,
            uri,
            METHOD,
            "pending",  # a candidate like any other: no reviewer has decided it
            None,
            term,
            marks,
            None,
            None,
            more.get("broader"),
            more.get("title_is", False),
        )

    def by_name(code_noted_as_same=None, category_noted=None, uri="u"):
        return (
            "2026-01",
            "by name",
            uri,
            "exact_title",
            "pending",
            None,
            None,
            None,
            code_noted_as_same,
            category_noted,
            None,
            False,
        )

    listed = "as listed in MONDO 2026-01-01"
    assert stored == {
        # "fever": one row for the code both routes reach, the name search's own, now noted as also reached through MONDO
        ("fever", ICD, "XZ01"): by_name(code_noted_as_same="XZ01"),
        ("fever", SNOMED, "111"): through_mondo(
            listed, "mondo name of fever", snomed_uri + "111", "MONDO:9000001", title_is=True
        ),
        # "other": two ICD-11 codes, one from each route, both candidates; WHO's official title, not MONDO's name
        ("other", ICD, "QQ99"): by_name(),
        ("other", ICD, "XZ01"): through_mondo("2026-01", "Synthetic fever disease", mms_uri, "MONDO:9000001"),
        ("other", SNOMED, "111"): through_mondo(
            listed, "mondo name of other", snomed_uri + "111", "MONDO:9000001", title_is=True
        ),
        # "grain": the category itself is added; the unspecified sub-code the name search stored is noted with it
        ("grain", ICD, "XZ01"): through_mondo("2026-01", "Synthetic fever disease", mms_uri, "MONDO:9000001"),
        ("grain", ICD, "XZ01.Z"): by_name(category_noted="XZ01", uri=f"{mms_uri}/unspecified"),
        ("grain", SNOMED, "111"): through_mondo(
            listed, "mondo name of grain", snomed_uri + "111", "MONDO:9000001", title_is=True
        ),
        ("unknown", SNOMED, "115"): through_mondo(
            listed, "mondo name of unknown", snomed_uri + "115", "MONDO:9000002", title_is=True
        ),
        # "young": WHO codes its entity under a broader one, so the link is the foundation entity itself
        ("young", ICD_FOUNDATION, "900006"): through_mondo(
            "2026-01",
            "Synthetic fever disease of the young",
            "http://id.who.int/icd/entity/900006",
            "MONDO:9000006",
            broader="XZ01",
        ),
    }

    with owner_db.transaction(None) as tx:  # the note says through which MONDO term the category was reached
        noted = tx.execute(
            text(
                """SELECT detail -> 'category_through_mondo' -> 'via' ->> 'code', detail -> 'category_through_mondo' ->> 'icd_title'
                   FROM terminology_links WHERE disease_id = :d AND code = 'XZ01.Z'"""
            ),
            {"d": ids["grain"]},
        ).one()
    assert tuple(noted) == ("MONDO:9000001", "Synthetic fever disease")

    path = write_review(result, tmp_path / "review")
    assert path.name == REVIEW_FILE
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert {(row["name"].split()[0], row["vocabulary"]) for row in rows} == {
        (key, vocabulary) for key in by for vocabulary in (SNOMED, ICD11)
    }
    related = next(row for row in rows if row["identifier"] == "112")
    assert (related["outcome"], related["marks"], related["stored_code"]) == (LINKED, "MONDO:relatedTo", "")
    chosen = next(row for row in rows if row["name"].startswith("other") and row["vocabulary"] == ICD11)
    assert (chosen["stored_as"], chosen["stored_code"], chosen["official_title"], chosen["agreement"]) == (
        ICD,
        "XZ01",
        "Synthetic fever disease",
        DIFFERENT,
    )
    broader = next(row for row in rows if row["name"].startswith("young") and row["vocabulary"] == ICD11)
    assert (broader["stored_as"], broader["stored_code"], broader["broader_mms_code"]) == (
        ICD_FOUNDATION,
        "900006",
        "XZ01",
    )
    # SNOMED CT's own name is not held, so the review file shows none for it.
    assert all(row["official_title"] == "" for row in rows if row["vocabulary"] == SNOMED)

    again = run()
    assert again["inserted"] == {SNOMED: 0, ICD: 0, ICD_FOUNDATION: 0} and check(again) == []
    assert again["who_calls"] == 0  # every answer was kept on disk

    # A reviewer rejects a MONDO link: it is no longer used, and the pending links that rest on it are reported.
    mine = {"l": f"tl_{tag}_other"}
    try:
        with owner_db.transaction(None) as tx:
            tx.execute(
                text(
                    "UPDATE terminology_links SET status = 'rejected', reviewer = 'dev-reviewer:test' WHERE link_id = :l"
                ),
                mine,
            )
        after = run()
        assert after["mondo_links"] == {"read": 8, "rejected_and_not_used": 2} and "other" not in {
            item["name"].split()[0] for item in after["items"]
        }
        assert check(after) == ["2 pending links rest on a MONDO link a reviewer has rejected"]
    finally:  # the count is taken over the whole table: leave nothing behind for other tests
        with owner_db.transaction(None) as tx:
            tx.execute(
                text("UPDATE terminology_links SET status = 'pending', reviewer = NULL WHERE link_id = :l"), mine
            )
    assert check(run()) == []


@pytest.mark.postgres
def test_an_entity_who_does_not_know_gives_no_link(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"who-{tag}.zip", "data.csv")
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"who-{tag}.zip/data.csv", version="t", sha256="0"))
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"fever {tag}"))
        tx.flush()
        tx.add(
            DiseaseMapping(
                mapping_id=f"dm_{tag}",
                release_id=RELEASE_ID,
                source_id=sid,
                original_label=f"fever {tag}",
                disease_id=f"dis_{tag}",
                method="lexical_casefold_whitespace",
            )
        )
        tx.flush()
        tx.execute(
            text(
                """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, uri, match_method)
                   VALUES (:l, :d, 'MONDO', '2026-01-01', 'MONDO:9000001', 'mondo name', 'u', 'exact_label')"""
            ),
            {"l": f"tl_{tag}", "d": f"dis_{tag}"},
        )
    entries = [entry(write_mondo(tmp_path / "mondo.owl"), "mondo_release")]
    client = IcdClient(SETTINGS, tmp_path / "cache", FakeWho({}), pause=0)
    result = import_identifiers(tmp_path, os.environ["TEST_MIGRATION_DATABASE_URL"], client, entries, [sid])
    assert check(result) == [] and result["inserted"] == {SNOMED: 1, ICD: 0, ICD_FOUNDATION: 0}
    record = result["items"][0]["outcomes"][ICD11]
    assert (record["outcome"], record["stored"], record["who"]) == (UNKNOWN_TO_WHO, None, None)


@pytest.mark.archives
def test_the_identifiers_in_the_registered_mondo_file_are_all_counted():
    registered = next((e for e in load_supplementary() if e.get("kind") == "mondo_release"), None)
    if registered is None or not (RAW_DIR / registered["name"]).is_file():
        pytest.skip("mondo.owl is not in data/raw")
    version, identifiers, counted = read_identifiers(RAW_DIR, registered)
    assert version == "2026-11-03"
    assert (
        sum(len(found) for found in identifiers.values())
        == counted[SNOMED]["identifiers"] + counted[ICD_FOUNDATION]["identifiers"]
    )
    heart_attack = {found.vocabulary: found for found in identifiers["MONDO:0005068"]}
    assert (heart_attack[SNOMED].number, heart_attack[SNOMED].equivalent) == ("22298006", True)
    assert counted[SNOMED]["marked_equivalent"] > 8000 and counted[ICD_FOUNDATION]["marked_equivalent"] > 4000
