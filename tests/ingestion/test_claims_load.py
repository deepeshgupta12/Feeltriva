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
            "kept_for_a_decision": 0,
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


def _under_earlier_rules(monkeypatch, url, ids):
    """Store the claims as earlier rules gave them: another version, under which no sentence ended inside a statement."""
    monkeypatch.setattr(claims, "VERSION", "claims-0")
    monkeypatch.setattr(claims, "sentences", lambda body: [(0, len(body))])
    early = extract_claims(url, ids)
    monkeypatch.undo()
    return early


def test_a_reviewer_s_decision_is_kept_when_the_rules_change(stored, owner_db, monkeypatch):
    """M2.5e2 (decision E72): a rule change does not lose a decision."""
    url, ids, tag = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"], stored["tag"]
    assert check(_under_earlier_rules(monkeypatch, url, ids)) == []

    def decide(status, where, value):
        with owner_db.transaction(None) as tx:
            changed = tx.execute(
                text(
                    f"UPDATE statement_claims SET status = :v, reviewer = 'dev-reviewer:test' "  # noqa: S608
                    f"WHERE statement_id = :s AND {where} = :t"
                ),
                {"v": status, "s": ids[0], "t": value},
            )
            assert changed.rowcount == 1

    def rows():
        with owner_db.transaction(None) as tx:
            found = tx.execute(
                text(
                    """SELECT c.claim_text, c.kind, c.status::text, c.rule, c.superseded_by, p.claim_text
                       FROM statement_claims c LEFT JOIN statement_claims p ON p.claim_id = c.parent_claim_id
                       WHERE c.statement_id = :s ORDER BY c.span_start, c.kind DESC, c.span_end"""
                ),
                {"s": ids[0]},
            ).all()
        return [tuple(row) for row in found]

    # A reviewer approves an item the present rules give too (under another sentence), and rejects the one long
    # sentence of the earlier rules, which the present rules no longer give.
    decide("approved", "claim_text", f"a hat {tag}")
    decide("rejected", "kind", "sentence")
    whole, first = stored["symptom"], stored["symptom"].removesuffix(" It ends.")
    # Not asked to make anything again: nothing is added, and the command says how to go on.
    plain = extract_claims(url, ids)
    assert plain["inserted"] == 0 and plain["earlier"] == {"claims": 4, "statements": 1, "reviewed_statements": 1}
    assert any(
        "a reviewer's decision" in diff and "--remake, which keeps every decision" in diff for diff in check(plain)
    )
    # Asked: the statement is brought to the present rules, and both decisions are still there.
    carried = extract_claims(url, ids, remake=True)
    assert carried["remade"] == {"statements": 0, "deleted": 0}
    # Two sentences stored; the two items the rules give again brought under the present sentence; the earlier last
    # item, which ran on to the end of the text and which nobody decided, deleted and made again by the present rules.
    assert carried["carried"] == {"statements": 1, "kept": 1, "adjusted": 2, "deleted": 1, "inserted": 2}
    assert check(carried) == [] and carried["inserted"] == 3
    assert rows() == [
        # the present first sentence, new and pending
        (first, "sentence", "pending", f"{VERSION}:sentence", None, None),
        # the long sentence of the earlier rules: decided, no longer given, kept as it is and marked
        (whole, "sentence", "rejected", "claims-0:sentence", VERSION, None),
        # the same claims as before: the approved one is still approved, now under the present sentence
        (f"a hat {tag}", "list_item", "approved", "claims-0:enumeration", None, first),
        (f"a scarf {tag} (red)", "list_item", "pending", "claims-0:enumeration", None, first),
        # the last item as the present rules give it
        (f"gloves {tag}", "list_item", "pending", f"{VERSION}:enumeration", None, first),
        ("It ends.", "sentence", "pending", f"{VERSION}:sentence", None, None),
    ]
    assert any("1 decided claims the rules no longer give kept and marked" in line for line in report(carried))
    # Nothing is left to do, and the kept claim is not reported again: by the command or by the completeness check.
    again = extract_claims(url, ids, remake=True)
    assert again["inserted"] == 0 and again["earlier"]["claims"] == 0 and check(again) == []
    assert again["carried"]["statements"] == 0
    with scratch(url) as cur:
        facts = _claims(cur, stored["sid"])
    assert (facts["expected"], facts["stored_as_expected"], facts["unexpected"], facts["kept_for_a_decision"]) == (
        5,
        5,
        0,
        1,
    )


def test_an_undecided_claim_under_a_kept_sentence_goes_and_the_sentence_stays(stored, owner_db, monkeypatch):
    url, ids, tag = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"], stored["tag"]
    _under_earlier_rules(monkeypatch, url, ids)
    with owner_db.transaction(None) as tx:
        # An item of the earlier rules that the present rules do not give at all, decided by a reviewer.
        tx.execute(
            text(
                """INSERT INTO statement_claims (claim_id, statement_id, parent_claim_id, kind, span_start, span_end,
                       claim_text, rule, cues, status, reviewer)
                   SELECT 'cl_old_' || :t, statement_id, claim_id, 'list_item', 0, 5, 'Signs', 'claims-0:enumeration',
                          '{}'::jsonb, 'rejected', 'dev-reviewer:test'
                   FROM statement_claims WHERE statement_id = :s AND kind = 'sentence'"""
            ),
            {"t": tag, "s": ids[0]},
        )
    carried = extract_claims(url, ids, remake=True)
    # The decided item is kept, and so is the undecided sentence it stands under. The one claim deleted is the
    # earlier last item, which nobody decided and the rules no longer give.
    assert carried["carried"]["kept"] == 2 and carried["carried"]["deleted"] == 1 and check(carried) == []
    with owner_db.transaction(None) as tx:
        kept = tx.execute(
            text(
                "SELECT kind, status::text, superseded_by FROM statement_claims "
                "WHERE statement_id = :s AND superseded_by IS NOT NULL ORDER BY kind"
            ),
            {"s": ids[0]},
        ).all()
    assert [tuple(row) for row in kept] == [("list_item", "rejected", VERSION), ("sentence", "pending", VERSION)]


def test_claims_the_rules_no_longer_give_are_made_again_only_when_asked(stored, owner_db, monkeypatch):
    url, ids, tag = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"], stored["tag"]

    def labels():
        with owner_db.transaction(None) as tx:
            rows = tx.execute(
                text("SELECT statement_id, rule, status::text FROM statement_claims WHERE statement_id = ANY(:s)"),
                {"s": ids},
            ).all()
        return sorted((row[0], row[1], row[2]) for row in rows)

    early = _under_earlier_rules(monkeypatch, url, ids)
    assert check(early) == [] and early["inserted"] == 5 and early["earlier"]["statements"] == 0

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

    # No reviewer has decided on any of them: the statement's claims are deleted and the present ones stored.
    assert tag in stored["symptom"]
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


def test_a_stored_claim_whose_cues_are_not_what_the_rules_give_is_made_again(stored, owner_db):
    # M2.6c: the wording cues of a claim are part of what the rules give.
    url, ids = os.environ["TEST_MIGRATION_DATABASE_URL"], stored["ids"]
    assert check(extract_claims(url, ids)) == []
    with owner_db.transaction(None) as tx:
        tx.execute(
            text("UPDATE statement_claims SET cues = '{}'::jsonb WHERE statement_id = :s AND kind = 'list_item'"),
            {"s": ids[0]},
        )
    plain = extract_claims(url, ids)
    assert plain["inserted"] == 0 and plain["earlier"] == {"claims": 3, "statements": 1, "reviewed_statements": 0}
    assert any("--remake" in diff for diff in check(plain))
    remade = extract_claims(url, ids, remake=True)
    assert remade["remade"] == {"statements": 1, "deleted": 5} and remade["inserted"] == 5 and check(remade) == []
    with owner_db.transaction(None) as tx:
        cues = tx.execute(
            text("SELECT DISTINCT cues FROM statement_claims WHERE statement_id = :s AND kind = 'list_item'"),
            {"s": ids[0]},
        ).all()
    assert [row[0] for row in cues] == [{"hedge": ["may"]}]


def test_the_length_at_which_a_source_cuts_its_texts_is_found_by_measurement(owner_db):
    """M2.5e2 (decision E74): a cut-off limit other than the 120 words of the one source measured by hand."""
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"cut-{tag}.zip", "summaries.csv")
    cut = "Word " * 7 + "signs include a hat, a scarf, gloves, and a"  # 16 words, stopped in the middle of a list
    assert len(cut.split()) == 16
    texts = [cut.replace("Word", f"Word{n}", 1) for n in range(6)] + ["A short text that ends."]
    with owner_db.transaction(None) as tx:
        tx.add(Source(source_id=sid, source_name=f"cut-{tag}.zip/summaries.csv", version="t", sha256="0"))
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend ache {tag}"))
        tx.flush()
        for number, body in enumerate(texts, start=1):
            tx.add(
                SourceRecord(
                    record_id=f"rec_{tag}_{number}",
                    source_id=sid,
                    file_path="summaries.csv",
                    row_number=number,
                    content_hash="0",
                    raw_object_uri="zip://x",
                )
            )
            tx.add(
                Statement(
                    statement_id=f"st_{tag}_{number}",
                    disease_id=f"dis_{tag}",
                    statement_type="description",
                    text_content=body,
                )
            )
            tx.flush()
            tx.add(StatementSource(statement_id=f"st_{tag}_{number}", record_id=f"rec_{tag}_{number}"))
    ids = [f"st_{tag}_{number}" for number in range(1, 8)]
    result = extract_claims(url, ids)
    assert check(result) == []
    # Six texts of this source have exactly 16 words and stop in the middle of a sentence: its limit is 16 words.
    assert result["cut_off"][sid] == 16
    assert any("by measurement" in line and "16" in line for line in report(result))
    with owner_db.transaction(None) as tx:
        marked = tx.execute(
            text(
                """SELECT statement_id, cues -> 'cut_off' FROM statement_claims
                   WHERE statement_id = ANY(:s) AND kind = 'sentence' ORDER BY statement_id, span_start"""
            ),
            {"s": ids},
        ).all()
        items = tx.execute(
            text(
                "SELECT claim_text FROM statement_claims WHERE statement_id = :s AND kind = 'list_item' ORDER BY span_start"
            ),
            {"s": ids[0]},
        ).all()
    assert [tuple(row) for row in marked] == [(ids[n], ["16 words"]) for n in range(6)] + [(ids[6], None)]
    # The last item of the list, a fragment, is not kept.
    assert [row[0] for row in items] == ["a hat", "a scarf", "gloves"]
