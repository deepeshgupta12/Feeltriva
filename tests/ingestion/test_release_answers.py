"""The answers behind the 0/1 of a derived file, taken from its source release (M2.13a).

Uses the crafted release and archive of test_release.py: one question that is not yes/no (`E_5`), whose
default answer "V_11" is listed like any other."""

from __future__ import annotations

import pytest
from feeltriva_ingestion.load import source_id
from feeltriva_ingestion.release import load_release
from feeltriva_ingestion.release_answers import answers_in, check, load_answers
from sqlalchemy import text

from tests.ingestion.test_release import crafted  # noqa: F401 - a fixture, used by name


def test_answers_are_read_from_an_evidence_list_as_they_are_written():
    wanted = frozenset({"E_54", "E_56", "E_204"})
    listed = "['E_48', 'E_54_@_V_161', 'E_54_@_V_112', 'E_55_@_V_29', 'E_56_@_6', 'E_204_@_V_10']"
    # Yes/no items and questions that were not asked for are left out; a number stays a number as written.
    assert answers_in(listed, wanted) == [("E_54", "V_161"), ("E_54", "V_112"), ("E_56", "6"), ("E_204", "V_10")]
    assert answers_in("[]", wanted) == [] and answers_in("['E_54']", wanted) == []


def test_every_kind_of_gap_is_reported():
    clean = {
        "not_in_release": 0,
        "trace_as_stored": True,
        "questions_mapped": 2,
        "rows_without_a_case": 0,
        "rows_where_answers_and_ones_differ": 0,
        "cells_affirmed": 5,
        "cells_answered": 5,
        "answers_not_among_the_possible": 0,
        "answers": 7,
        "stored_answers": 7,
        "stored_cells": 5,
    }

    def diffs(**changed):
        return check(
            {"releases": {"r.zip": {"questions": ["E_1", "E_2"], "files": {"a.zip/f.csv": {**clean, **changed}}}}}
        )

    assert diffs() == []
    assert "3 rows are not in the release" in diffs(not_in_release=3)[0]
    assert "run load-release first" in diffs(trace_as_stored=False)[0]
    assert "1 of 2 questions have a column mapping" in diffs(questions_mapped=1)[0]
    assert "2 rows have no loaded case" in diffs(rows_without_a_case=2)[0]
    assert "differ in 1 rows (5 1s, 4 answered)" in diffs(rows_where_answers_and_ones_differ=1, cells_answered=4)[0]
    assert "1 answers are not among those the dictionary lists" in diffs(answers_not_among_the_possible=1)[0]
    assert "7 answers in 5 cells read, 6 in 5 stored" in diffs(stored_answers=6)[0]


@pytest.mark.postgres
def test_each_answer_is_stored_with_the_release_row_it_came_from(crafted, owner_db):  # noqa: F811
    directory, url, entry, archive, tag = (crafted[key] for key in ("dir", "url", "entry", "archive", "tag"))
    before = load_answers(directory, url, [entry])  # the files have not been traced to the release yet
    assert [diff.split(": ", 1)[1] for diff in check(before)][:2] == [
        "the rows are traced differently from what load-release stored; run load-release first",
        "nothing was read or stored",
    ]
    with owner_db.transaction(None) as tx:
        assert (
            tx.execute(
                text("SELECT count(*) FROM case_answers WHERE mapping_id LIKE :m"), {"m": f"fm_{tag}_%"}
            ).scalar_one()
            == 0
        )
    load_release(directory, url, [entry])
    result = load_answers(directory, url, [entry])
    assert check(result) == []
    facts = result["releases"][entry["name"]]
    assert facts["questions"] == ["E_5"]
    train, test = facts["files"][f"{archive}/train.csv"], facts["files"][f"{archive}/test.csv"]
    # train.csv: 5 rows, 2 of them with a 1 in the E_5 column; the second answer is the publisher's default.
    assert (train["rows"], train["cells_affirmed"], train["cells_answered"], train["answers"]) == (5, 2, 2, 2)
    assert (train["answers_that_are_the_default"], train["stored_cells"], train["stored_cases"]) == (1, 2, 2)
    # test.csv: one case gave two answers to the one question.
    assert (test["rows"], test["cells_affirmed"], test["cells_answered"], test["answers"]) == (2, 1, 1, 2)
    assert (test["stored_answers"], test["stored_cells"], test["stored_cases"]) == (2, 1, 1)
    assert test["per_question"] == [("E_5_characterize_your_pain", 2, 1, 2)]
    with owner_db.transaction(None) as tx:
        stored = tx.execute(
            text(
                """SELECT s.source_name, r.row_number, a.mapping_id, a.answer, a.source_id, a.release_split, a.release_row
                   FROM case_answers a JOIN dataset_cases c USING (case_id) JOIN source_records r USING (record_id)
                   JOIN sources s ON s.source_id = r.source_id WHERE a.mapping_id LIKE :m ORDER BY 1, 2, 4"""
            ),
            {"m": f"fm_{tag}_%"},
        ).all()
        untouched = tx.execute(
            text("SELECT count(*) FROM case_features WHERE mapping_id LIKE :m"), {"m": f"fm_{tag}_%"}
        ).scalar_one()
    release = source_id(entry["name"], "*")
    assert [tuple(row) for row in stored] == [
        # our row 1 of test.csv is row 1 of the release's test set; both of its answers are kept
        (f"{archive}/test.csv", 1, f"fm_{tag}_te_4", "V_11", release, "test", 1),
        (f"{archive}/test.csv", 1, f"fm_{tag}_te_4", "V_20", release, "test", 1),
        # our row 1 of train.csv is row 1 of the train set; our row 4 is row 1 of the validation set
        (f"{archive}/train.csv", 1, f"fm_{tag}_tr_4", "V_20", release, "train", 1),
        (f"{archive}/train.csv", 4, f"fm_{tag}_tr_4", "V_11", release, "validate", 1),
    ]
    assert untouched == 0  # the loader writes answers only; it stores or changes no 0/1 value
    again = load_answers(directory, url, [entry])
    assert check(again) == []
    assert [info["inserted"] for info in again["releases"][entry["name"]]["files"].values()] == [0, 0]
