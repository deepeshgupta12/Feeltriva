"""Deriving and storing feature-meaning proposals on crafted archives (PostgreSQL only).

Three small archives: one with a symptom matrix and the same cases as symptom lists, one with a
questionnaire (question headings, ages, a column that is 1 in every row, two questions answered
as a block), and one that presents a term as a symptom through its column prefix.
"""

from __future__ import annotations

import csv
import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.lists import feature_candidate_id, load_symptom_lists
from feeltriva_ingestion.load import RELEASE_ID, source_id
from feeltriva_ingestion.meanings import UNDECIDED, VERSION
from feeltriva_ingestion.meanings_load import check, derive_meanings, summarise, write_review
from sqlalchemy import text

pytestmark = pytest.mark.postgres
TARGETS = ["source_records", "dataset_cases", "case_labels"]
QUESTIONS = (
    "do_you_have_a_fever",  # names a symptom two other archives present
    "have_you_ever_had_a",  # the past; cut off
    "have_you_traveled_out_of",  # an exposure; 1 in every row
    "how_intense_is_the_pain",  # a description; answered together with the next one
    "where_is_the_pain_located",
    "do_you_have_a_problem",  # nothing settles it
    "does_your_mother_suffer_from",  # relatives
)


@pytest.fixture
def crafted(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    fever, cough, family = f"fever {tag}", f"cough {tag}", f"family history {tag}"
    a, b, c = f"mean-a-{tag}.zip", f"mean-b-{tag}.zip", f"mean-c-{tag}.zip"
    with zipfile.ZipFile(tmp_path / a, "w") as z:
        under = [term.replace(" ", "_") for term in (fever, cough, family)]
        z.writestr("data.csv", f"diseases,{','.join(under)}\nFlu,1,1,0\nFlu,1,0,0\nCold,0,1,1\nAsthma,0,1,0\n")
        z.writestr(  # the Flu and Cold cases again, as lists, in another order
            "lists.csv", f'diseases,symptom_text\nCold,"{cough}, {family}"\nFlu,"{fever}, {cough}"\nFlu,"{fever}"\n'
        )
    headings = [f"E_{n}_{question}" + (f"_{tag}" if n == 1 else "") for n, question in enumerate(QUESTIONS, start=1)]
    rows = []
    for k in range(120):
        block = "1" if k < 110 else "0"
        answers = [str(k % 2), str(int(k % 3 == 0)), "1", block, block, str(int(k % 5 == 0)), str(int(k % 7 == 0))]
        rows.append(f"{k},{20 + k % 60},{'MF'[k % 2]},{'Flu' if k % 2 else 'Cold'},{','.join(answers)}")
    with zipfile.ZipFile(tmp_path / b, "w") as z:
        z.writestr("survey.csv", f"PATIENT_ID,AGE,SEX,DISEASE,{','.join(headings)}\n" + "\n".join(rows) + "\n")
    with zipfile.ZipFile(tmp_path / c, "w") as z:
        z.writestr("c.csv", f"disease,symptom_{fever.replace(' ', '_')}\nFlu,1\nCold,0\n")
    matrix = {"adapter": "positional_feature_matrix", "targets": TARGETS}
    manifest = Manifest(
        {name: sha256_file(tmp_path / name) for name in (a, b, c)},
        [
            {"archive": a, "file": "data.csv", "expected_rows": 4, "exact_unique_rows": 4, **matrix},
            {
                "archive": a,
                "file": "lists.csv",
                "expected_rows": 3,
                "exact_unique_rows": 3,
                "adapter": "symptom_list",
                "targets": TARGETS,
            },
            {"archive": b, "file": "survey.csv", "expected_rows": 120, "exact_unique_rows": 120, **matrix},
            {"archive": c, "file": "c.csv", "expected_rows": 2, "exact_unique_rows": 2, **matrix},
        ],
        [],
    )
    columns = {
        (a, "data.csv"): [(1, under[0], fever), (2, under[1], cough), (3, under[2], family)],
        (b, "survey.csv"): [(n + 3, heading, None) for n, heading in enumerate(headings, start=1)],
        (c, "c.csv"): [(1, f"symptom_{fever.replace(' ', '_')}", fever)],
    }
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        for entry in manifest.files:
            sid = source_id(entry["archive"], entry["file"])
            tx.add(Source(source_id=sid, source_name=f"{entry['archive']}/{entry['file']}", version="t", sha256="0"))
        tx.flush()
        for (archive, file), cols in columns.items():
            for index, heading, term in cols:
                feature_id = feature_candidate_id(term) if term else f"feat_{tag}_q{index}"
                if tx.get(Feature, feature_id) is None:
                    tx.add(
                        Feature(
                            feature_id=feature_id, preferred_name=term or heading, kind="other", value_type="boolean"
                        )
                    )
                    tx.flush()
                tx.add(
                    FeatureMapping(
                        mapping_id=f"fm_{tag}_{file[:2]}_{index}",
                        release_id=RELEASE_ID,
                        source_id=source_id(archive, file),
                        file_path=file,
                        column_index=index,
                        original_term=heading,
                        feature_id=feature_id,
                        transformation={"candidate_term": term} if term else {},
                    )
                )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    load_symptom_lists(tmp_path, url, manifest)  # registers the list terms as pending mappings
    return {"dir": tmp_path, "url": url, "manifest": manifest, "tag": tag, "archives": (a, b, c), "headings": headings}


def _by(result, file):
    return {p["original_term"]: p["meaning"] for p in result["proposals"] if p["file"] == file}


def test_proposals_are_derived_stored_pending_and_reproducible(crafted, owner_db, tmp_path):
    tag, (a, b, _c) = crafted["tag"], crafted["archives"]
    result = derive_meanings(crafted["dir"], crafted["url"], crafted["manifest"])
    assert check(result) == []
    data, lists, survey, other = (_by(result, file) for file in ("data.csv", "lists.csv", "survey.csv", "c.csv"))
    e = dict(zip(QUESTIONS, crafted["headings"], strict=True))

    # Kind: from what the source says and from the wording; relatives and the past are never symptoms.
    assert (data[f"fever_{tag}"]["kind"], data[f"fever_{tag}"]["kind_rule"]) == ("symptom", "stated_by_source")
    assert "the same archive lists the term in `lists.csv:symptom_text`" in data[f"fever_{tag}"]["kind_basis"]
    assert data[f"family_history_{tag}"]["kind"] == "history"  # the wording decides over the source's label
    assert lists[f"family history {tag}"]["kind"] == "history" and lists[f"cough {tag}"]["kind"] == "symptom"
    assert other[f"symptom_fever_{tag}"]["kind_basis"].startswith("the source presents it as a symptom (column prefix")
    kinds = {question: (survey[e[question]]["kind"], survey[e[question]]["kind_rule"]) for question in QUESTIONS}
    assert kinds == {
        "do_you_have_a_fever": ("symptom", "names_a_symptom"),
        "have_you_ever_had_a": ("history", "past_event"),
        "have_you_traveled_out_of": ("risk_factor", "exposure_or_lifestyle"),
        "how_intense_is_the_pain": ("symptom", "description_of_a_symptom"),
        "where_is_the_pain_located": ("symptom", "description_of_a_symptom"),
        "do_you_have_a_problem": (UNDECIDED, "none"),
        "does_your_mother_suffer_from": ("history", "relatives"),
    }
    assert f"names 'fever {tag}'" in survey[e["do_you_have_a_fever"]]["kind_basis"]
    assert survey[e["have_you_ever_had_a"]]["question_cut_off"] is True

    # Zero: what the files show, and never a denial.
    assert {m["zero_rule"] for m in data.values()} == {"same_cases_as_lists"}  # the list file holds the same cases
    assert {m["zero"] for m in data.values()} == {"not_recorded"} == {m["zero"] for m in lists.values()}
    assert result["twins"] == {"data.csv": {"list_file": "lists.csv", "labels": 2, "rows": 3}}
    travelled, intense = survey[e["have_you_traveled_out_of"]], survey[e["how_intense_is_the_pain"]]
    assert (travelled["zero"], travelled["zero_rule"], travelled["one_means"]) == (
        "no_answer",
        "affirmed_in_every_row",
        "an answer was recorded",
    )
    assert (travelled["affirmed_cases"], travelled["cases"]) == (120, 120)
    assert (intense["zero"], intense["zero_rule"], intense["affirmed_cases"]) == ("no_answer", "recorded_together", 110)
    assert e["where_is_the_pain_located"] in intense["zero_basis"]
    fever_question = survey[e["do_you_have_a_fever"]]
    assert (fever_question["zero"], fever_question["zero_rule"], fever_question["one_means"]) == (
        "unknown",
        "no_evidence",
        "affirmed",
    )
    assert other[f"symptom_fever_{tag}"]["zero"] == "unknown"

    # Age: a proposal on the source, not a value on the cases.
    survey_sid = source_id(b, "survey.csv")
    age = result["populations"][survey_sid]["age"]
    assert (age["column"], age["minimum"], age["maximum"], age["whole_numbers"], age["unit_proposed"]) == (
        "AGE",
        20,
        79,
        True,
        "years",
    )
    with owner_db.transaction(None) as tx:
        stored = tx.execute(
            text(
                """SELECT m.original_term, m.zero_semantics, m.status::text, m.transformation -> 'meaning', f.kind::text,
                          f.status::text
                   FROM feature_mappings m JOIN features f USING (feature_id) WHERE m.source_id = ANY(:s)"""
            ),
            {"s": [source_id(entry["archive"], entry["file"]) for entry in crafted["manifest"].files]},
        ).all()
        population = tx.execute(
            text("SELECT population FROM sources WHERE source_id = :s"), {"s": survey_sid}
        ).scalar_one()
        units = tx.execute(
            text(
                "SELECT count(*) FROM dataset_cases c JOIN source_records r USING (record_id) WHERE r.source_id = :s AND c.age_unit IS NOT NULL"
            ),
            {"s": survey_sid},
        ).scalar_one()
        twin = tx.execute(
            text("SELECT population FROM sources WHERE source_id = :s"), {"s": source_id(a, "data.csv")}
        ).scalar_one()
    assert len(stored) == len(result["proposals"]) == 3 + 3 + 7 + 1
    assert {row[2] for row in stored} == {"pending"} == {row[5] for row in stored}  # nothing is approved
    assert all(row[3]["version"] == VERSION and row[3]["status"] == "proposal, pending review" for row in stored)
    assert all(row[1] == row[3]["zero"] and row[1] != "absent" for row in stored)
    by_term = {row[0]: row[4] for row in stored}
    assert by_term[f"fever_{tag}"] == "symptom" and by_term[f"family_history_{tag}"] == "history"
    assert by_term[e["have_you_traveled_out_of"]] == "risk_factor" and by_term[e["do_you_have_a_problem"]] == "other"
    assert population["age"]["unit_proposed"] == "years" and units == 0  # the unit is proposed, not written to cases
    assert twin["same_cases_as"]["file"] == "lists.csv" and twin["same_cases_as"]["rows"] == 3
    assert result["changed"]["mappings"] == 14 and result["changed"]["left_alone_already_reviewed"] == 0

    again = derive_meanings(crafted["dir"], crafted["url"], crafted["manifest"])
    assert again["changed"] == {"mappings": 0, "features": 0, "sources": 0, "left_alone_already_reviewed": 0}
    assert [p["meaning"] for p in again["proposals"]] == [p["meaning"] for p in result["proposals"]]

    table, document = write_review(result, tmp_path / "review")
    with table.open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 14 and {row["kind"] for row in written} == {"symptom", "history", "risk_factor", UNDECIDED}
    page = document.read_text(encoding="utf-8")
    assert (
        "proposal, pending review" in page and "## Undecided: 1 headings the wording cannot settle (1 columns)" in page
    )
    assert f"`{e['do_you_have_a_problem']}`" in page and "**Same cases twice.** All 3 rows of `lists.csv`" in page
    assert (
        "| years |" in page and "affirmed in every row" in page and "## 3 columns that are not yes/no answers" in page
    )
    counts = summarise(result)
    assert (
        counts["kinds"][(f"{b[8:10]} survey.csv", "history")] == 2
        and counts["zeros"][(f"{b[8:10]} survey.csv", "no_answer")] == 3
    )


def test_a_reviewers_decision_is_never_overwritten(crafted, owner_db):
    tag = crafted["tag"]
    with owner_db.transaction(None) as tx:
        tx.execute(
            text(
                "UPDATE feature_mappings SET status = 'approved', zero_semantics = 'decided by a reviewer' WHERE mapping_id = :m"
            ),
            {"m": f"fm_{tag}_da_1"},
        )
        tx.execute(
            text("UPDATE features SET status = 'approved', kind = 'sign' WHERE feature_id = :f"),
            {"f": feature_candidate_id(f"cough {tag}")},
        )
    result = derive_meanings(crafted["dir"], crafted["url"], crafted["manifest"])
    assert result["changed"]["left_alone_already_reviewed"] == 1 and result["stored"]["not_pending"] == 1
    assert check(result) == []
    with owner_db.transaction(None) as tx:
        mapping = tx.execute(
            text("SELECT zero_semantics, transformation ? 'meaning' FROM feature_mappings WHERE mapping_id = :m"),
            {"m": f"fm_{tag}_da_1"},
        ).one()
        feature = tx.execute(
            text("SELECT kind::text FROM features WHERE feature_id = :f"), {"f": feature_candidate_id(f"cough {tag}")}
        ).scalar_one()
    assert tuple(mapping) == ("decided by a reviewer", False) and feature == "sign"
