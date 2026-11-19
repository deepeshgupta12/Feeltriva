"""What a source release says about its conditions, stored as pending source-provided rows (M2.13b).

Uses the crafted release and archive of test_release.py, with a conditions file written here."""

from __future__ import annotations

import json
import zipfile

import pytest
from feeltriva_ingestion.archives import sha256_file
from feeltriva_ingestion.load import source_id
from feeltriva_ingestion.release import load_release
from feeltriva_ingestion.release_conditions import (
    EVIDENCE_TYPE,
    FILE,
    ICD10,
    METHOD,
    SEVERITY,
    check,
    load_conditions,
    record_id,
)
from feeltriva_ingestion.vocabulary import link_id
from sqlalchemy import text

from tests.ingestion.test_release import crafted  # noqa: F401 - a fixture, used by name

# E_1 and E_5 are symptoms in the crafted dictionary; E_2, E_3 and E_4 are antecedents.
CONDITIONS = {
    "Flu": {
        "condition_name": "Flu",
        "cond-name-fr": "Grippe",
        "cond-name-eng": "Flu",
        "icd10-id": "j11.1x",  # written as a publisher might: lower case, with a suffix
        "severity": 3,
        "symptoms": {"E_1": {}, "E_5": {}, "E_2": {}},  # E_2 is an antecedent in the dictionary
        "antecedents": {"E_3": {}},
    },
    "Cold": {
        "condition_name": "Cold",
        "cond-name-fr": "Rhume",
        "cond-name-eng": "Cold",
        "icd10-id": "J00",
        "severity": 5,
        "symptoms": {"E_1": {}},
        "antecedents": {"E_4": {}, "E_2": {}},
    },
}


def _with_conditions(crafted, conditions):  # noqa: F811
    """Rewrite the crafted release with a real conditions file and return its registry entry."""
    path = crafted["dir"] / crafted["entry"]["name"]
    with zipfile.ZipFile(path) as old:
        members = {name: old.read(name) for name in old.namelist()}
    members[FILE] = json.dumps(conditions).encode()
    with zipfile.ZipFile(path, "w") as new:
        for name, data in members.items():
            new.writestr(name, data)
    return {**crafted["entry"], "sha256": sha256_file(path)}


def test_every_kind_of_gap_is_reported():
    clean = {
        "conditions": 2,
        "ready": True,
        "without_one_disease": [],
        "codes_without_one_feature": [],
        "expected_evidence": 7,
        "with_a_code": 2,
        "stored_records": 2,
        "stored_evidence": {"rows": 7, "without_a_record": 0},
        "stored_links": {"rows": 2, "decided_without_reviewer": 0},
    }

    def diffs(**changed):
        return check({"releases": {"r.zip": {**clean, **changed}}})

    assert diffs() == []
    assert "run load-release first. Nothing was written" in diffs(ready=False)[0]
    assert (
        "'Gout' is not the label of exactly one disease candidate"
        in diffs(without_one_disease=["Gout"], stored_records=1)[0]
    )
    assert "Flu: E_9 is not the question of exactly one feature" in diffs(codes_without_one_feature=["Flu: E_9"])[0]
    assert "2 conditions read, 1 source records stored" in diffs(stored_records=1)[0]
    assert (
        "7 listed questions read, 6 evidence rows stored"
        in diffs(stored_evidence={"rows": 6, "without_a_record": 0})[0]
    )
    assert (
        "2 conditions carry a code, 1 links stored" in diffs(stored_links={"rows": 1, "decided_without_reviewer": 0})[0]
    )
    assert "(1 decided without a reviewer)" in diffs(stored_links={"rows": 2, "decided_without_reviewer": 1})[0]


@pytest.mark.postgres
def test_a_release_s_condition_lists_become_pending_evidence_and_its_codes_pending_links(crafted, owner_db):  # noqa: F811
    directory, url, tag = crafted["dir"], crafted["url"], crafted["tag"]
    # The codes carry the run's tag: a link is one disease and one code, and the test database keeps earlier runs.
    flu_code, cold_code = f"j11.1x{tag}", f"J00{tag}"
    conditions = {
        "Flu": {**CONDITIONS["Flu"], "icd10-id": flu_code},
        "Cold": {**CONDITIONS["Cold"], "icd10-id": cold_code},
    }
    entry = _with_conditions(crafted, conditions)
    release = source_id(entry["name"], "*")
    before = load_conditions(directory, url, [entry])  # the release has not been registered yet
    assert "run load-release first. Nothing was written" in check(before)[0]
    load_release(directory, url, [entry])
    result = load_conditions(directory, url, [entry])
    assert check(result) == []
    facts = result["releases"][entry["name"]]
    assert (facts["conditions"], facts["listed"], facts["expected_evidence"]) == (
        2,
        {"symptoms": 4, "antecedents": 3},
        7,
    )
    assert facts["inserted"] == {"records": 2, "evidence": 7, "links": 2} and facts["severity"] == {"3": 1, "5": 1}
    # A question the publisher lists under symptoms although its own dictionary calls it an antecedent is kept as listed.
    assert facts["listed_against_the_dictionary"] == ["Flu: E_2 listed as symptom"]
    assert facts["stored_evidence"] == {"rows": 7, "pending": 7, "diseases": 2, "features": 5, "without_a_record": 0}
    assert facts["stored_links"] == {"rows": 2, "pending": 2, "decided_without_reviewer": 0}
    with owner_db.transaction(None) as tx:
        evidence = tx.execute(
            text(
                """SELECT d.preferred_name, e.context ->> 'question_code', e.relationship, e.status::text, e.evidence_type,
                          e.context ->> 'listed_as', e.context ->> 'dictionary_says', r.source_id, r.file_path, r.row_number,
                          f.feature_id
                   FROM disease_feature_evidence e JOIN diseases d USING (disease_id) JOIN source_records r USING (record_id)
                   JOIN features f USING (feature_id) WHERE e.context ->> 'source_id' = :s ORDER BY 1, 2"""
            ),
            {"s": release},
        ).all()
        links = tx.execute(
            text(
                """SELECT d.preferred_name, t.system, t.code, t.title, t.uri, t.match_method, t.status::text, t.reviewer,
                          t.detail ->> 'record_id'
                   FROM terminology_links t JOIN diseases d USING (disease_id) WHERE t.detail ->> 'source_id' = :s ORDER BY 1"""
            ),
            {"s": release},
        ).all()
        kept = tx.execute(text("SELECT population FROM sources WHERE source_id = :s"), {"s": release}).scalar_one()
    listed = [(row[0], row[1], row[2].split("_")[2], row[5], row[6], row[9]) for row in evidence]
    assert listed == [
        ("cold", "E_1", "symptom", "symptom", "symptom", 2),
        ("cold", "E_2", "antecedent", "antecedent", "antecedent", 2),
        ("cold", "E_4", "antecedent", "antecedent", "antecedent", 2),
        ("flu", "E_1", "symptom", "symptom", "symptom", 1),
        ("flu", "E_2", "symptom", "symptom", "antecedent", 1),
        ("flu", "E_3", "antecedent", "antecedent", "antecedent", 1),
        ("flu", "E_5", "symptom", "symptom", "symptom", 1),
    ]
    # Every row is pending, of the one evidence type, and points at the record of the condition entry it came from.
    assert {(row[3], row[4], row[7], row[8]) for row in evidence} == {("pending", EVIDENCE_TYPE, release, FILE)}
    assert {row[10] for row in evidence} <= {f"feat_{tag}_{n}" for n in range(5)}
    assert [tuple(row) for row in links] == [
        ("cold", ICD10, cold_code, "Cold", None, METHOD, "pending", None, record_id(release, 2)),
        ("flu", ICD10, flu_code, "Flu", None, METHOD, "pending", None, record_id(release, 1)),  # the code as written
    ]
    assert kept["severity_as_documented"] == SEVERITY
    assert {
        name: (c["severity"], c["icd10_as_written"], c["name_fr"], c["symptoms"], c["antecedents"])
        for name, c in kept["conditions"].items()
    } == {
        "Flu": (3, flu_code, "Grippe", 3, 1),
        "Cold": (5, cold_code, "Rhume", 1, 2),
    }
    assert "origin" not in kept or kept["origin"]  # what load-release stored on the row, if anything, is still there
    again = load_conditions(directory, url, [entry])
    assert check(again) == [] and again["releases"][entry["name"]]["inserted"] == {
        "records": 0,
        "evidence": 0,
        "links": 0,
    }


@pytest.mark.postgres
def test_a_condition_that_is_no_label_of_ours_is_reported_and_a_link_already_there_is_no_gap(crafted, owner_db):  # noqa: F811
    entry = _with_conditions(
        crafted, {**CONDITIONS, "Gout": {**CONDITIONS["Cold"], "condition_name": "Gout", "symptoms": {"E_99": {}}}}
    )
    load_release(crafted["dir"], crafted["url"], [entry])
    # Another source has already said the same code for "cold": the link exists before this release is loaded.
    version = "as written in the source release; edition not stated"
    with owner_db.transaction(None) as tx:
        cold = tx.execute(
            text(
                """SELECT DISTINCT l.disease_id FROM case_labels l JOIN dataset_cases c USING (case_id)
                   JOIN source_records r USING (record_id) WHERE r.source_id = :s AND l.original_label = 'Cold'"""
            ),
            {"s": source_id(crafted["archive"], "train.csv")},
        ).scalar_one()
        tx.execute(
            text(
                """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, match_method)
                   VALUES (:l, :d, :y, :v, 'J00', 'Cold', 'source_provided') ON CONFLICT (link_id) DO NOTHING"""
            ),
            {"l": link_id(cold, ICD10, version, "J00"), "d": cold, "y": ICD10, "v": version},
        )
    result = load_conditions(crafted["dir"], crafted["url"], [entry])
    diffs = check(result)
    facts = result["releases"][entry["name"]]
    assert any("'Gout' is not the label of exactly one disease candidate" in diff for diff in diffs)
    assert facts["stored_records"] == 2  # the two known conditions only
    # The link that was already there is found, not stored again, and not reported as missing.
    assert facts["stored_links"]["rows"] == facts["with_a_code"] == 2 and facts["inserted"]["links"] <= 1
    assert not any("links stored" in diff for diff in diffs)
