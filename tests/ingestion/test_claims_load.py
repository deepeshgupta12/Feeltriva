"""The single claims of stored statements in the review queue (M2.6). Invented statements."""

from __future__ import annotations

import os
import uuid

import pytest
from feeltriva_api.models import (
    Disease,
    Feature,
    FeatureMapping,
    MappingRelease,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from feeltriva_ingestion import claims
from feeltriva_ingestion.claims import VERSION
from feeltriva_ingestion.claims_load import check, claim_id, extract_claims, report
from feeltriva_ingestion.completeness import _claims
from feeltriva_ingestion.load import RELEASE_ID, source_id
from sqlalchemy import text

from tests.ingestion.test_completeness import scratch

pytestmark = pytest.mark.postgres


@pytest.fixture
def stored(owner_db):
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"claims-{tag}.zip", "symptoms.csv")
    symptom = f"Signs may include a hat {tag}, a scarf {tag} (red), and gloves {tag}. It ends."
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"claims-{tag}.zip/symptoms.csv", version="t", sha256="0"))
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend ache {tag}"))
        # One feature is named exactly like the first item; two features share the name of the second.
        for key, name in (("hat", f"hat {tag}"), ("scarf1", f"scarf {tag}"), ("scarf2", f"scarf_{tag}")):
            tx.add(Feature(feature_id=f"feat_{tag}_{key}", preferred_name=name, kind="symptom", value_type="boolean"))
        tx.flush()
        for column, key in enumerate(("hat", "scarf1", "scarf2"), start=1):
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{key}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    file_path="symptoms.csv",
                    column_index=column,
                    original_term=f"{key} {tag}",
                    feature_id=f"feat_{tag}_{key}",
                )
            )
        for number, (kind, body) in enumerate((("symptom", symptom), ("treatment", "Use a coat.")), start=1):
            tx.add(
                SourceRecord(
                    record_id=f"rec_{tag}_{number}",
                    source_id=sid,
                    file_path="symptoms.csv",
                    row_number=number,
                    content_hash="0",
                    raw_object_uri="zip://x",
                )
            )
            tx.add(
                Statement(
                    statement_id=f"st_{tag}_{number}", disease_id=f"dis_{tag}", statement_type=kind, text_content=body
                )
            )
            tx.flush()
            tx.add(
                StatementSource(
                    statement_id=f"st_{tag}_{number}",
                    record_id=f"rec_{tag}_{number}",
                    source_url="https://example.org/a",
                )
            )
    return {"tag": tag, "sid": sid, "symptom": symptom, "ids": [f"st_{tag}_1", f"st_{tag}_2"]}


def test_claims_are_stored_pending_with_their_span_their_sentence_and_a_feature_named_exactly(stored, owner_db):
    tag, ids, symptom = stored["tag"], stored["ids"], stored["symptom"]
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    result = extract_claims(url, ids)
    assert check(result) == [] and result["version"] == VERSION
    assert dict(result["statements"]) == {"symptom": 1, "treatment": 1}
    assert dict(result["claims"]) == {
        ("symptom", "sentence"): 2,
        ("symptom", "list_item"): 3,
        ("treatment", "sentence"): 1,
    }
    # The first item is the name of one feature, the second of two (so of none), the third of none.
    assert dict(result["features"]) == {"one feature": 1, "several": 1, "none": 1}
    assert (result["inserted"], result["expected_rows"]) == (6, 6) and dict(result["cues"]) == {"hedge": 1}
    assert result["stored"] == {
        "rows": 6,
        "pending": 6,
        "decided_without_reviewer": 0,
        "not_the_text_at_their_span": 0,
        "statements_with_sentences": 2,
        "with_a_proposed_feature": 1,
        "with_applicability": 0,
        "without_a_source": 0,
    }
    assert any("3 list items" in line for line in report(result))
    with owner_db.transaction(None) as tx:
        rows = tx.execute(
            text(
                """SELECT c.kind, c.claim_text, c.span_start, c.span_end, c.parent_claim_id, c.status::text, c.reviewer,
                          c.proposed_feature_id, c.applicability, c.rule, c.cues, s.source_url
                   FROM statement_claims c JOIN statement_sources s USING (statement_id)
                   WHERE c.statement_id = :s ORDER BY c.span_start, c.kind DESC"""
            ),
            {"s": ids[0]},
        ).all()
    first = f"Signs may include a hat {tag}, a scarf {tag} (red), and gloves {tag}."
    sentence = claim_id(ids[0], "sentence", 0, len(first))
    assert [(row[0], row[1], row[4]) for row in rows] == [
        ("sentence", first, None),
        ("list_item", f"a hat {tag}", sentence),
        ("list_item", f"a scarf {tag} (red)", sentence),
        ("list_item", f"gloves {tag}", sentence),
        ("sentence", "It ends.", None),
    ]
    assert all(symptom[row[2] : row[3]] == row[1] for row in rows)  # every claim is the statement's text at its offsets
    # Pending, undecided, no applicability set, and reachable to its source through its statement.
    assert {(row[5], row[6], row[8], row[11]) for row in rows} == {("pending", None, None, "https://example.org/a")}
    assert [row[7] for row in rows] == [None, f"feat_{tag}_hat", None, None, None]
    assert rows[1][9] == f"{VERSION}:enumeration" and rows[1][10] == {"hedge": ["may"]}

    # A second run stores nothing, and a reviewer's decision stays.
    with owner_db.transaction(None) as tx:
        tx.execute(
            text("UPDATE statement_claims SET status = 'rejected', reviewer = 'dev-reviewer:test' WHERE claim_id = :c"),
            {"c": sentence},
        )
    again = extract_claims(url, ids)
    assert again["inserted"] == 0 and check(again) == [] and again["stored"]["pending"] == 5

    # The completeness facts recompute the claims of the symptom statements and compare them with what is stored.
    with scratch(url) as cur:
        assert _claims(cur, stored["sid"]) == {
            "statements": 1,
            "expected": 5,
            "stored_as_expected": 5,
            "unexpected": 0,
            "not_their_text": 0,
            "decided_without_reviewer": 0,
        }
        cur.execute(
            "DELETE FROM statement_claims WHERE statement_id = %s AND claim_text = %s", (ids[0], f"gloves {tag}")
        )
        cur.execute(
            "UPDATE statement_claims SET claim_text = 'other words' WHERE statement_id = %s AND claim_text = 'It ends.'",
            (ids[0],),
        )
        cur.execute("UPDATE statement_claims SET reviewer = NULL WHERE claim_id = %s", (sentence,))
        damaged = _claims(cur, stored["sid"])
        assert (damaged["stored_as_expected"], damaged["not_their_text"], damaged["decided_without_reviewer"]) == (
            4,
            1,
            1,
        )


def test_a_stored_claim_that_is_no_longer_its_statement_s_text_is_reported(stored, owner_db):
    url, ids = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"]
    assert check(extract_claims(url, ids)) == []
    with owner_db.transaction(None) as tx:
        tx.execute(text("UPDATE statements SET text_content = 'Use two coats.' WHERE statement_id = :s"), {"s": ids[1]})
    changed = extract_claims(url, ids)
    assert "1 stored claims are not their statement's text at their offsets" in check(changed)


def test_claims_the_rules_no_longer_give_are_made_again_only_when_asked_and_never_after_a_decision(
    stored, owner_db, monkeypatch
):
    url, ids, tag = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"], stored["tag"]

    def labels():
        with owner_db.transaction(None) as tx:
            rows = tx.execute(
                text("SELECT statement_id, rule, status::text FROM statement_claims WHERE statement_id = ANY(:s)"),
                {"s": ids},
            ).all()
        return sorted((row[0], row[1], row[2]) for row in rows)

    # Earlier rules: another version, under which no sentence was ended inside a statement.
    monkeypatch.setattr(claims, "VERSION", "claims-0")
    monkeypatch.setattr(claims, "sentences", lambda body: [(0, len(body))])
    early = extract_claims(url, ids)
    assert check(early) == [] and early["inserted"] == 5 and early["earlier"]["statements"] == 0
    monkeypatch.undo()

    # The present rules, not asked to make anything again. The first statement holds a sentence and an item the rules
    # no longer give, and two items that now belong to another sentence: nothing is added to it, and it is reported.
    # The second statement's one claim is what the present rules give too: it stays, with the label it was made under.
    plain = extract_claims(url, ids)
    assert plain["inserted"] == 0 and plain["stored"]["rows"] == 5
    assert plain["earlier"] == {"claims": 4, "statements": 1, "reviewed_statements": 0}
    assert plain["remade"] == {"statements": 0, "deleted": 0}
    assert any(
        "1 statements hold claims that the rules do not give" in diff and "--remake" in diff for diff in check(plain)
    )
    assert any("4 in 1 statements" in line for line in report(plain))

    # A reviewer has decided on one of them: the statement is left as it is, also when asked to make it again.
    with owner_db.transaction(None) as tx:
        tx.execute(
            text(
                """UPDATE statement_claims SET status = 'approved', reviewer = 'dev-reviewer:test'
                   WHERE statement_id = :s AND claim_text = :t"""
            ),
            {"s": ids[0], "t": f"a hat {tag}"},
        )
    kept = extract_claims(url, ids, remake=True)
    assert kept["inserted"] == 0 and kept["remade"] == {"statements": 0, "deleted": 0}
    assert kept["earlier"] == {"claims": 4, "statements": 1, "reviewed_statements": 1}
    diffs = check(kept)
    assert any(
        "1 statements hold claims that the rules do not give and a reviewer's decision" in diff for diff in diffs
    )
    assert not any("--remake" in diff for diff in diffs)
    assert (ids[0], "claims-0:enumeration", "approved") in labels()

    # Without a decision, the statement's claims are deleted and the present ones stored.
    with owner_db.transaction(None) as tx:
        tx.execute(
            text("UPDATE statement_claims SET status = 'pending', reviewer = NULL WHERE statement_id = :s"),
            {"s": ids[0]},
        )
    remade = extract_claims(url, ids, remake=True)
    assert remade["remade"] == {"statements": 1, "deleted": 4} and remade["inserted"] == 5
    assert check(remade) == [] and remade["stored"]["rows"] == 6 and remade["stored"]["pending"] == 6
    assert labels() == sorted(
        [(ids[0], f"{VERSION}:sentence", "pending")] * 2
        + [(ids[0], f"{VERSION}:enumeration", "pending")] * 3
        + [(ids[1], "claims-0:sentence", "pending")]
    )
    # Nothing is left to make again.
    again = extract_claims(url, ids, remake=True)
    assert again["inserted"] == 0 and again["earlier"]["statements"] == 0 and check(again) == []
