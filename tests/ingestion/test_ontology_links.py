"""Candidate links to HPO and MONDO stored for review (M2.14). Invented vocabulary files; nothing leaves the machine."""

from __future__ import annotations

import csv
import os
import uuid

import pytest
from feeltriva_api.models import Disease, DiseaseMapping, Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import RAW_DIR
from feeltriva_ingestion.load import RELEASE_ID, source_id
from feeltriva_ingestion.ontologies import (
    ABBREVIATION_ONLY,
    HPO,
    KINDS,
    LINKED,
    MONDO,
    NOT_LINKABLE,
    NOTHING,
    SENTENCE,
    lookup,
    read_vocabulary,
)
from feeltriva_ingestion.ontology_links import REVIEW_FILE, check, link_ontologies, summarise, write_review
from feeltriva_ingestion.release import load_supplementary
from sqlalchemy import text

from tests.ontology_fixtures import entry, write_hpo, write_mondo


def test_the_command_needs_a_registered_file():
    with pytest.raises(SystemExit, match="no HPO or MONDO file is registered"):
        link_ontologies(entries=[{"name": "Loinc.zip", "kind": "loinc_release"}], database_url="postgresql://unused")


@pytest.mark.postgres
def test_exact_names_become_pending_links_and_every_name_gets_a_recorded_outcome(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"onto-{tag}.zip", "data.csv")
    fever, short, glow, unknown = (
        f"synthetic fever disease {tag}",
        f"sfd {tag}",
        f"synthetic glow {tag}",
        f"unheard thing {tag}",
    )
    question = f"E_1_do_you_glow_{tag}"
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"onto-{tag}.zip/data.csv", version="t", sha256="0"))
        for n, name in enumerate((fever, short, glow, unknown)):
            tx.add(Disease(disease_id=f"dis_{tag}_{n}", preferred_name=name))
        tx.add(
            Feature(
                feature_id=f"feat_{tag}_s",
                preferred_name=f"shining skin {tag} symptom",
                kind="symptom",
                value_type="boolean",
            )
        )
        tx.add(Feature(feature_id=f"feat_{tag}_q", preferred_name=question, kind="symptom", value_type="boolean"))
        tx.flush()
        for n, name in enumerate((fever, short, glow, unknown)):
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{n}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    original_label=name,
                    disease_id=f"dis_{tag}_{n}",
                    method="lexical_casefold_whitespace",
                )
            )
        for column, (key, term) in enumerate((("s", f"symptom_shining_skin_{tag}"), ("q", question)), start=1):
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{key}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    file_path="data.csv",
                    column_index=column,
                    original_term=term,
                    feature_id=f"feat_{tag}_{key}",
                )
            )
        tx.flush()
        # A link to another vocabulary for the same disease: it must stay out of the review file.
        tx.execute(
            text(
                """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, uri, match_method)
                   VALUES (:l, :d, 'ICD-11 MMS', 'test', :c, 't', 'u', 'exact_title')"""
            ),
            {"l": f"tl_{tag}_icd", "d": f"dis_{tag}_0", "c": f"XA{tag}"},
        )
    entries = [
        entry(write_hpo(tmp_path / "hp.json", tag=tag), "hpo_release"),
        entry(write_mondo(tmp_path / "mondo.owl", tag=tag), "mondo_release"),
        {"name": "Loinc.zip", "kind": "loinc_release"},  # another kind of registered file is ignored
    ]
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]

    def run():
        return link_ontologies(tmp_path, url, entries, [sid])

    result = run()
    assert check(result) == []
    assert [(v.system, v.version) for v in result["vocabularies"]] == [(HPO, "2026-01-01"), (MONDO, "2026-01-01")]
    assert result["inserted"] == {HPO: 2, MONDO: 1}
    by = {item["name"]: item for item in result["items"]}
    assert len(by) == 6 and all(set(item["outcomes"]) == {HPO, MONDO} for item in by.values())
    assert [(link["system"], link["code"], link["method"]) for link in by[fever]["links"]] == [
        (MONDO, "MONDO:9000001", "exact_label")
    ]
    assert by[short]["links"] == [] and by[short]["outcomes"][MONDO].outcome == ABBREVIATION_ONLY
    assert [c.code for c in by[short]["outcomes"][MONDO].candidates] == ["MONDO:9000001"]
    assert [(link["system"], link["code"]) for link in by[glow]["links"]] == [(HPO, "HP:9000001")]
    assert {o.outcome for o in by[unknown]["outcomes"].values()} == {NOTHING}
    symptom = by[f"shining skin {tag} symptom"]
    assert symptom["looked_up"] == f"shining skin {tag}"  # the naming word "symptom" is dropped
    assert [(link["code"], link["method"], link["detail"]["synonym_type"]) for link in symptom["links"]] == [
        ("HP:9000001", "exact_synonym", "layperson")
    ]
    assert by[question]["looked_up"] == "" and {o.outcome for o in by[question]["outcomes"].values()} == {SENTENCE}
    assert set(result["case_labels"]) == {
        "all",
        "label_linked_here",
        "label_linked_in_another_vocabulary",
        "label_linked_anywhere",
    }
    counts = summarise(result)
    assert counts["groups"] == {"disease labels": 4, "feature terms": 2}
    assert counts["rows"][("disease labels", MONDO, "linked: our name is the term's label")] == 1
    assert counts["rows"][("feature terms", HPO, "linked: our name is an exact synonym")] == 1
    assert counts["linked"] == {
        ("disease labels", "linked in at least one of them"): 2,
        ("disease labels", "looked up, no link in either"): 2,
        ("feature terms", "linked in at least one of them"): 1,
    }

    with owner_db.transaction(None) as tx:
        stored = tx.execute(
            text(
                """SELECT coalesce(disease_id, feature_id), system, system_version, code, title, uri, match_method,
                          status::text, detail ->> 'branch', detail ->> 'matched_text'
                   FROM terminology_links WHERE (disease_id LIKE :d OR feature_id LIKE :f) AND system <> 'ICD-11 MMS'
                   ORDER BY 1, 2"""
            ),
            {"d": f"dis_{tag}_%", "f": f"feat_{tag}_%"},
        ).all()
    assert [tuple(row) for row in stored] == [
        (
            f"dis_{tag}_0",
            MONDO,
            "2026-01-01",
            "MONDO:9000001",
            f"synthetic fever disease {tag}",
            "http://purl.obolibrary.org/obo/MONDO_9000001",
            "exact_label",
            "pending",
            "human disease",
            f"synthetic fever disease {tag}",
        ),
        (
            f"dis_{tag}_2",
            HPO,
            "2026-01-01",
            "HP:9000001",
            f"Synthetic glow {tag}",
            "http://purl.obolibrary.org/obo/HP_9000001",
            "exact_label",
            "pending",
            "Phenotypic abnormality",
            f"Synthetic glow {tag}",
        ),
        (
            f"feat_{tag}_s",
            HPO,
            "2026-01-01",
            "HP:9000001",
            f"Synthetic glow {tag}",
            "http://purl.obolibrary.org/obo/HP_9000001",
            "exact_synonym",
            "pending",
            "Phenotypic abnormality",
            f"Shining skin {tag}",
        ),
    ]

    # The review file: one row per item and vocabulary, a reason wherever there is no link, and no
    # code of another vocabulary (the ICD-11 link of the same disease is not in it).
    path = write_review(result, tmp_path / "review")
    assert path.name == REVIEW_FILE
    body = path.read_text(encoding="utf-8")
    assert f"XA{tag}" not in body and "ICD" not in body
    rows = list(csv.DictReader(body.splitlines()))
    assert len(rows) == 12 and {(row["name"], row["system"]) for row in rows} == {
        (name, system) for name in by for system in (HPO, MONDO)
    }
    assert all((row["outcome"] == LINKED) == bool(row["code"]) for row in rows)
    assert all(row["reason"] for row in rows if row["outcome"] != LINKED)
    abbreviation = next(row for row in rows if row["name"] == short and row["system"] == MONDO)
    assert abbreviation["outcome"] == ABBREVIATION_ONLY and "MONDO:9000001" in abbreviation["candidates"]

    # A reviewer's decision survives a second run, and nothing is stored twice.
    with owner_db.transaction(None) as tx:
        tx.execute(
            text(
                """UPDATE terminology_links SET status = 'rejected', reviewer = 'dev-reviewer:test'
                   WHERE disease_id = :d AND system = 'MONDO'"""
            ),
            {"d": f"dis_{tag}_0"},
        )
    again = run()
    assert again["inserted"] == {HPO: 0, MONDO: 0} and check(again) == []
    with owner_db.transaction(None) as tx:
        kept = tx.execute(
            text(
                """SELECT status::text, reviewer, count(*) OVER () FROM terminology_links
                   WHERE disease_id = :d AND system = 'MONDO'"""
            ),
            {"d": f"dis_{tag}_0"},
        ).one()
    assert tuple(kept) == ("rejected", "dev-reviewer:test", 1)

    # A decision nobody signed is reported; the reviewer's name is put back so that no other test sees it.
    mine = {"d": f"dis_{tag}_0"}
    try:
        with owner_db.transaction(None) as tx:
            tx.execute(
                text("UPDATE terminology_links SET reviewer = NULL WHERE disease_id = :d AND system = 'MONDO'"), mine
            )
        assert check(run()) == ["1 stored MONDO links are rejected without a recorded reviewer"]
    finally:
        with owner_db.transaction(None) as tx:
            tx.execute(
                text(
                    "UPDATE terminology_links SET reviewer = 'dev-reviewer:test' WHERE disease_id = :d AND system = 'MONDO'"
                ),
                mine,
            )


@pytest.mark.archives
def test_the_registered_files_are_read_whole_and_the_known_hazards_get_no_link():
    """The real `hp.json` and `mondo.owl` (skipped when they are not in data/raw)."""
    entries = {KINDS[e["kind"]]: e for e in load_supplementary() if e.get("kind") in KINDS}
    if not all((RAW_DIR / e["name"]).is_file() for e in entries.values()):
        pytest.skip("hp.json and mondo.owl are not in data/raw")
    hpo, mondo = read_vocabulary(RAW_DIR, entries[HPO]), read_vocabulary(RAW_DIR, entries[MONDO])
    counted = hpo.inventory
    assert (hpo.version, counted["terms"], counted["current"], counted["obsolete"], counted["linkable"]) == (
        "2026-09-01",
        20482,
        19894,
        588,
        19845,
    )
    assert sum(counted["by_branch"].values()) == counted["current"] and counted["parent_links"] == 24436
    counted = mondo.inventory
    assert (mondo.version, counted["terms"], counted["current"], counted["obsolete"], counted["linkable"]) == (
        "2026-11-03",
        36168,
        32137,
        4031,
        23285,
    )
    assert (
        counted["by_branch"]["non-human animal disease"] == 8319 and counted["entries_of_other_vocabularies"] == 27627
    )
    # A common word that is also an abbreviation of something else is not linked.
    for name in ("scar", "cold", "ards", "gerd"):
        found = lookup(mondo, name)
        assert (found.outcome, found.link) == (ABBREVIATION_ONLY, None) and found.candidates, name
    # A name shared with the animal form of a disease is linked to the human disease only.
    myeloma = lookup(mondo, "multiple myeloma")
    assert (myeloma.link.code, myeloma.link.branch, myeloma.link.how) == (
        "MONDO:0009693",
        "human disease",
        "exact_synonym",
    )
    assert lookup(mondo, "heart attack").link.code == "MONDO:0005068"
    assert lookup(mondo, "frostbite").link.branch == "injury"
    assert lookup(hpo, "ataxia symptom").link.code == "HP:0001251"
    assert lookup(mondo, "ataxia symptom").link is None  # MONDO has it only as a looser synonym and an animal term
    assert lookup(hpo, "mood swings").outcome == NOT_LINKABLE  # the only HPO term with this name is obsolete
