"""Tracing our files to a supplied source release and using its question dictionary (M2.12).

A crafted release with the layout of the real one (two JSON files, three patient files, each in
its own inner ZIP) and a crafted archive whose train file is built the way the real one is:
rows of the release's train set, a gap, then the whole validation set.
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import ArchiveError, Manifest, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.load import RELEASE_ID, source_id
from feeltriva_ingestion.meanings_load import derive_meanings
from feeltriva_ingestion.release import check, load_release
from sqlalchemy import text

pytestmark = pytest.mark.postgres
TARGETS = ["source_records", "dataset_cases", "case_labels"]
QUESTIONS = {
    "E_1": ("Do you have a fever (either felt or measured)?", False, "B", "do_you_have_a_fever"),
    "E_2": ("Have you ever had a heart attack?", True, "B", "have_you_ever_had_a"),
    "E_3": ("Do you smoke cigarettes?", True, "B", "do_you_smoke_cigarettes"),
    "E_4": ("Do you have a problem with poor circulation?", True, "B", "do_you_have_a_problem"),
    "E_5": ("Characterize your pain:", False, "M", "characterize_your_pain"),
}
PATIENTS = {  # (age, sex, condition, evidences)
    "train": [
        (30, "F", "Flu", ["E_1", "E_5_@_V_20"]),
        (31, "M", "Flu", ["E_2"]),
        (32, "F", "Cold", ["E_3"]),
        (33, "M", "Cold", ["E_1", "E_4"]),
    ],
    "validate": [(40, "F", "Flu", ["E_5_@_V_11"]), (41, "M", "Cold", [])],
    "test": [(50, "F", "Flu", ["E_1", "E_2", "E_5_@_V_20", "E_5_@_V_11"]), (51, "M", "Cold", ["E_3"])],
}


def _inner(rows):
    table = io.StringIO()
    writer = csv.writer(table)
    writer.writerow(["AGE", "DIFFERENTIAL_DIAGNOSIS", "SEX", "PATHOLOGY", "EVIDENCES", "INITIAL_EVIDENCE"])
    for age, sex, condition, evidences in rows:
        writer.writerow([age, "[]", sex, condition, str(evidences), evidences[0] if evidences else ""])
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("patients", table.getvalue())
    return data.getvalue()


def _ours(rows, headings):
    lines = ["PATIENT_ID,AGE,SEX,DISEASE," + ",".join(headings) + ",SYMPTOM_COUNT"]
    for n, (age, sex, condition, evidences) in enumerate(rows, start=1):
        codes = {item.split("_@_")[0] for item in evidences}
        cells = ["1" if code in codes else "0" for code in QUESTIONS]
        lines.append(f"{n},{age},{sex},{condition},{','.join(cells)},{sum(cell == '1' for cell in cells)}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def crafted(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    release_name, archive = f"release-{tag}.zip", f"questions-{tag}.zip"
    evidences = {
        code: {
            "name": code,
            "code_question": code,
            "question_en": question,
            "question_fr": "",
            "is_antecedent": antecedent,
            "data_type": answer_type,
            "default_value": 0 if answer_type == "B" else "V_11",
            "possible-values": [] if answer_type == "B" else ["V_11", "V_20"],
            "value_meaning": {}
            if answer_type == "B"
            else {"V_11": {"en": "NA", "fr": "NA"}, "V_20": {"en": "sharp", "fr": "vive"}},
        }
        for code, (question, antecedent, answer_type, _heading) in QUESTIONS.items()
    }
    with zipfile.ZipFile(tmp_path / release_name, "w") as z:
        z.writestr("release_evidences.json", json.dumps(evidences))
        z.writestr("release_conditions.json", json.dumps({"Flu": {}, "Cold": {}}))
        for split, rows in PATIENTS.items():
            z.writestr(f"release_{split}_patients.zip", _inner(rows))
    headings = [f"{code}_{heading}" for code, (_q, _a, _t, heading) in QUESTIONS.items()]
    train = [PATIENTS["train"][0], PATIENTS["train"][1], PATIENTS["train"][3], *PATIENTS["validate"]]
    with zipfile.ZipFile(tmp_path / archive, "w") as z:
        z.writestr("train.csv", _ours(train, headings))
        z.writestr("test.csv", _ours(PATIENTS["test"], headings))
    matrix = {"adapter": "positional_feature_matrix", "targets": TARGETS}
    manifest = Manifest(
        {archive: sha256_file(tmp_path / archive)},
        [
            {"archive": archive, "file": "train.csv", "expected_rows": 5, "exact_unique_rows": 5, **matrix},
            {"archive": archive, "file": "test.csv", "expected_rows": 2, "exact_unique_rows": 2, **matrix},
        ],
        [],
    )
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        for file in ("train.csv", "test.csv"):
            tx.add(Source(source_id=source_id(archive, file), source_name=f"{archive}/{file}", version="t", sha256="0"))
        for n in range(len(headings)):
            tx.add(
                Feature(feature_id=f"feat_{tag}_{n}", preferred_name=headings[n], kind="other", value_type="boolean")
            )
        tx.flush()
        for file in ("train.csv", "test.csv"):
            for n, heading in enumerate(headings):
                tx.add(
                    FeatureMapping(
                        mapping_id=f"fm_{tag}_{file[:2]}_{n}",
                        release_id=RELEASE_ID,
                        source_id=source_id(archive, file),
                        file_path=file,
                        column_index=n + 4,
                        original_term=heading,
                        feature_id=f"feat_{tag}_{n}",
                    )
                )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    entry = {
        "name": release_name,
        "sha256": sha256_file(tmp_path / release_name),
        "kind": "ddxplus_release",
        "title": f"Crafted release {tag}",
        "doi": f"10.0000/crafted.{tag}",
        "origin_url": "https://example.org/release",
        "licence": "CC BY 4.0",
        "publisher_statement": "The dataset contains patients synthesized for a test.",
        "describes": [{"archive": archive, "file": "train.csv"}, {"archive": archive, "file": "test.csv"}],
    }
    return {
        "dir": tmp_path,
        "url": url,
        "manifest": manifest,
        "entry": entry,
        "archive": archive,
        "tag": tag,
        "headings": headings,
    }


def test_files_are_traced_to_the_release_and_its_dictionary_settles_the_kinds(crafted, owner_db):
    archive, entry, tag = crafted["archive"], crafted["entry"], crafted["tag"]
    result = load_release(crafted["dir"], crafted["url"], [entry])
    assert check(result) == []
    facts = result["releases"][entry["name"]]
    assert (facts["questions"], facts["antecedents"], facts["answer_types"]) == (5, 3, {"B": 4, "M": 1})
    assert facts["release_rows"] == {"train": 4, "validate": 2, "test": 2}
    train, test = facts["files"][f"{archive}/train.csv"], facts["files"][f"{archive}/test.csv"]
    runs = [(r["our_first_row"], r["release_split"], r["release_first_row"], r["rows"]) for r in train["runs"]]
    assert runs == [
        (1, "train", 1, 2),
        (3, "train", 4, 1),
        (4, "validate", 1, 2),
    ]  # our "train" includes the validation set
    assert (train["rows"], train["traced"], train["not_in_release"]) == (5, 5, 0) and test["runs"][0][
        "release_split"
    ] == "test"
    assert (
        train["mappings_with_a_dictionary_entry"] == train["headings_that_start_the_question"] == train["mappings"] == 5
    )
    assert facts["changed"] == {"mappings": 10, "sources": 3}

    with owner_db.transaction(None) as tx:
        stored = dict(
            tx.execute(
                text(
                    "SELECT original_term, transformation -> 'source_dictionary' FROM feature_mappings WHERE source_id = :s"
                ),
                {"s": source_id(archive, "train.csv")},
            ).all()
        )
        release_source = tx.execute(
            text("SELECT licence, origin_url, version, provenance_status::text FROM sources WHERE source_id = :s"),
            {"s": source_id(entry["name"], "*")},
        ).one()
        described = tx.execute(
            text(
                "SELECT licence, origin_url, population -> 'origin', provenance_status::text FROM sources WHERE source_id = :s"
            ),
            {"s": source_id(archive, "train.csv")},
        ).one()
    fever, pain = stored[crafted["headings"][0]], stored[crafted["headings"][4]]
    assert (fever["question"], fever["is_antecedent"], fever["answer_type"], fever["default_value"]) == (
        "Do you have a fever (either felt or measured)?",
        False,
        "yes_no",
        0,
    )
    assert (pain["answer_type"], pain["default_value"], pain["values"]) == (
        "several_of_several",
        "V_11",
        {"V_11": "NA", "V_20": "sharp"},
    )
    assert tuple(release_source) == ("CC BY 4.0", "https://example.org/release", entry["doi"], "pending")
    assert described[0] == "CC BY 4.0" and described[3] == "pending"  # recorded, not approved
    assert described[2]["publisher_statement"].startswith("The dataset contains patients synthesized")
    assert (described[2]["rows"], described[2]["rows_traced_to_the_release"]) == (5, 5)

    assert load_release(crafted["dir"], crafted["url"], [entry])["releases"][entry["name"]]["changed"] == {
        "mappings": 0,
        "sources": 0,
    }

    # With the dictionary in place the kinds come from the source's own flag, and nothing is undecided.
    derived = derive_meanings(crafted["dir"], crafted["url"], crafted["manifest"])
    by = {p["original_term"]: p["meaning"] for p in derived["proposals"] if p["file"] == "train.csv"}
    found = {
        code: (by[h]["kind"], by[h]["kind_rule"], by[h]["zero"])
        for code, h in zip(QUESTIONS, crafted["headings"], strict=True)
    }
    assert found == {
        "E_1": ("symptom", "source_dictionary", "no_per_source"),
        "E_2": ("history", "source_dictionary+past_event", "no_per_source"),
        "E_3": ("risk_factor", "source_dictionary+exposure_or_lifestyle", "no_per_source"),
        "E_4": (
            "history",
            "source_dictionary",
            "no_per_source",
        ),  # "do you have a problem" was undecided from wording alone
        "E_5": ("symptom", "source_dictionary", "no_answer"),
    }
    assert by[crafted["headings"][3]]["question"] == "Do you have a problem with poor circulation?"
    assert derived["stored"]["zero_as_denial"] == 0 and derived["stored"]["not_pending"] == 0
    with owner_db.transaction(None) as tx:
        kinds = dict(
            tx.execute(
                text("SELECT feature_id, kind::text FROM features WHERE feature_id LIKE :p"), {"p": f"feat_{tag}_%"}
            ).all()
        )
    assert [kinds[f"feat_{tag}_{n}"] for n in range(5)] == ["symptom", "history", "risk_factor", "history", "symptom"]


def test_a_changed_release_file_or_a_row_it_does_not_contain_is_reported(crafted, owner_db):
    entry, archive = crafted["entry"], crafted["archive"]
    with pytest.raises(ArchiveError, match="does not match the registered"):
        load_release(crafted["dir"], crafted["url"], [{**entry, "sha256": "0" * 64}])
    with pytest.raises(ArchiveError, match="missing from"):
        load_release(crafted["dir"], crafted["url"], [{**entry, "name": "absent.zip"}])
    # A release that lacks one of our rows: the origin is then not established for that file.
    smaller = crafted["dir"] / f"smaller-{crafted['tag']}.zip"
    with zipfile.ZipFile(crafted["dir"] / entry["name"]) as full, zipfile.ZipFile(smaller, "w") as z:
        for name in full.namelist():
            z.writestr(name, _inner(PATIENTS["test"][:1]) if name == "release_test_patients.zip" else full.read(name))
    result = load_release(
        crafted["dir"], crafted["url"], [{**entry, "name": smaller.name, "sha256": sha256_file(smaller)}]
    )
    assert check(result) == [f"{archive}/test.csv: 1 rows are not in {smaller.name}"]
