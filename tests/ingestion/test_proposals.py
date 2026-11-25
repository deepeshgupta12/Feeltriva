"""Rows stored for a reviewer by the look-ups (M2.4b): what a row must hold, and what a later run does to it."""

from __future__ import annotations

import os
import uuid

import pytest
from feeltriva_api import review_proposals
from feeltriva_api.models import Disease, ReviewNote
from feeltriva_ingestion import proposals
from feeltriva_ingestion.cases import _raw_cursor
from sqlalchemy import create_engine, text


def test_the_review_service_and_the_look_ups_name_the_same_kinds_of_row():
    written = {
        value
        for name, value in vars(proposals).items()
        if name.isupper() and isinstance(value, str) and name != "TARGET"
    }
    assert written == set(review_proposals.KINDS) and proposals.TARGET == review_proposals.TARGET
    assert review_proposals.CONFIRMABLE <= set(review_proposals.KINDS)
    # A row that only records a reason is never one a reviewer can confirm.
    assert not {proposals.NO_TERM, proposals.SENTENCE, proposals.NOT_LINKABLE} & set(review_proposals.CONFIRMABLE)


def test_a_row_names_a_whole_term_and_the_link_it_would_make_or_neither():
    item = {"type": "feature", "id": "feat_x", "name": "x"}
    term = {"code": "HP:1", "title": "One", "uri": "http://example.invalid/1"}
    made = proposals.row(item, "HPO", "v1", proposals.NEAREST, "why", term, "tl_1", matched_text="one", note="")
    assert (made["feature_id"], made["disease_id"], made["code"], made["link_id"]) == ("feat_x", None, "HP:1", "tl_1")
    assert made["detail"] == {"matched_text": "one"}  # an empty detail is not stored
    bare = proposals.row(item, "HPO", "v1", proposals.NO_TERM, "why", None, None)
    assert (bare["code"], bare["title"], bare["uri"], bare["link_id"]) == (None, None, None, None)
    assert bare["proposal_id"] != made["proposal_id"] and made["proposal_id"].startswith("lp_")
    with pytest.raises(ValueError, match="or neither"):
        proposals.row(item, "HPO", "v1", proposals.NEAREST, "why", term, None)
    with pytest.raises(ValueError, match="code, title and address together"):
        proposals.row(item, "ICD-11 MMS", "v1", proposals.CLOSE_RESULT, "why", {**term, "uri": ""}, "tl_1")


@pytest.mark.postgres
def test_a_full_run_removes_what_is_out_of_date_but_never_a_decided_or_noted_row(owner_db):
    tag = uuid.uuid4().hex[:10]
    kind = f"test_kind_{tag}"  # a kind of its own, so that the full run touches no other test's rows
    with owner_db.transaction(None) as tx:
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"invented {tag}"))
    item = {"type": "disease", "id": f"dis_{tag}", "name": f"invented {tag}"}

    def made(code):
        term = {"code": code, "title": f"Term {code}", "uri": f"http://example.invalid/{code}"}
        return proposals.row(item, "HPO", "v1", kind, "invented reason", term, f"tl_{tag}_{code}")

    rows = [made(code) for code in ("a", "b", "c", "d")]
    engine = create_engine(os.environ["TEST_MIGRATION_DATABASE_URL"])

    def store(given, complete):
        with _raw_cursor(engine) as cur:
            return proposals.store(cur, given, bases=(kind,), complete=complete)

    def codes():
        with owner_db.transaction(None) as tx:
            found = tx.execute(text("SELECT code FROM link_proposals WHERE basis = :b ORDER BY code"), {"b": kind})
            return [row[0] for row in found]

    try:
        first = store([*rows, rows[0]], complete=True)
        assert (first["given"], first["given_twice"], first["inserted"], first["missing"]) == (4, 1, 4, 0)
        assert proposals.check(first) == ["1 proposals were given twice for one name, vocabulary and term"]
        with owner_db.transaction(None) as tx:  # "b" is decided by a reviewer, "c" carries a note
            tx.execute(
                text(
                    "UPDATE link_proposals SET status = 'rejected', reviewer = 'dev-reviewer:t' WHERE proposal_id = :p"
                ),
                {"p": rows[1]["proposal_id"]},
            )
            tx.add(
                ReviewNote(
                    note_id=uuid.uuid4(),
                    target_type=proposals.TARGET,
                    target_id=rows[2]["proposal_id"],
                    reviewer="dev-reviewer:t",
                    note="look at this again",
                )
            )
        # A run over some sources only removes nothing, whatever it gives.
        part = store(rows[:1], complete=False)
        assert (part["removed_out_of_date"], part["kept_not_given"], part["inserted"]) == (0, None, 0)
        assert codes() == ["a", "b", "c", "d"]
        # A full run that gives only "a" again: "d" is out of date and goes; the decided and the noted row stay.
        full = store(rows[:1], complete=True)
        assert (full["removed_out_of_date"], full["kept_not_given"], full["inserted"]) == (1, 2, 0)
        assert codes() == ["a", "b", "c"] and proposals.check(full) == []
        assert [(row[0], row[2], row[3], row[4]) for row in full["table"]] == [
            (kind, "pending", 2, 2),
            (kind, "rejected", 1, 1),
        ]
        assert "1 out of date and removed, 2 kept from an earlier run" in proposals.lines(full)[0]
    finally:
        engine.dispose()
