"""Single claims and text chunks in the review path, and what an approval makes (M2.5e). Invented rows."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api.models import (
    Disease,
    DiseaseFeatureEvidence,
    EvidenceChunk,
    Feature,
    KnowledgeRelease,
    MappingRelease,
    PublishedKnowledge,
    Source,
    SourceRecord,
    Statement,
    StatementClaim,
    StatementSource,
)
from feeltriva_api.review_claims import evidence_id_of, statement_id_of
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

CLAIMS = "/internal/v1/review/claims"
CHUNKS = "/internal/v1/review/chunks"
DECIDE = "/internal/v1/review/decisions"
SENTENCE = "Signs include a pretend hat, a scarf and a coat."
PART = "People with a pretend ache often wear a hat. This part of the text says so."


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def world(owner_db) -> str:
    """One invented symptom statement with a sentence and two list items (one names a feature), and three parts
    of an invented text file: one under "Signs and symptoms", the opening part, and a list of references."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"map-{tag}", version=f"map-{tag}-0"))
        tx.add(Source(source_id=f"src_{tag}", source_name=f"sample-{tag}", version="1", sha256=f"sha-{tag}"))
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend ache {tag}"))
        tx.add(Feature(feature_id=f"feat_{tag}", preferred_name=f"hat {tag}", kind="symptom", value_type="boolean"))
        tx.flush()
        tx.add(
            KnowledgeRelease(
                release_id=f"know-{tag}",
                mapping_release_id=f"map-{tag}",
                version=f"know-{tag}-0",
                manifest_uri=f"test://know-{tag}",
            )
        )
        for key, row in (("s", 1), ("t", None)):
            tx.add(
                SourceRecord(
                    record_id=f"rec_{tag}_{key}",
                    source_id=f"src_{tag}",
                    file_path="symptoms.csv" if row else f"pretend_ache_{tag}.txt",
                    row_number=row,
                    content_hash=f"hash-{tag}-{key}",
                    raw_object_uri=f"test://{tag}/{key}",
                )
            )
        tx.flush()
        tx.add(
            Statement(
                statement_id=f"st_{tag}", disease_id=f"dis_{tag}", statement_type="symptom", text_content=SENTENCE
            )
        )
        tx.flush()
        tx.add(
            StatementSource(statement_id=f"st_{tag}", record_id=f"rec_{tag}_s", source_url="https://example.org/sample")
        )
        tx.add(
            StatementClaim(
                claim_id=f"cl_{tag}_s",
                statement_id=f"st_{tag}",
                kind="sentence",
                span_start=0,
                span_end=len(SENTENCE),
                claim_text=SENTENCE,
                rule="test:sentence",
                cues={},
            )
        )
        tx.flush()
        for key, word, feature, cues in (
            ("hat", "a pretend hat", f"feat_{tag}", {"first_item_preposition": ["of"]}),
            ("scarf", "a scarf", None, {}),
        ):
            start = SENTENCE.index(word)
            tx.add(
                StatementClaim(
                    claim_id=f"cl_{tag}_{key}",
                    statement_id=f"st_{tag}",
                    parent_claim_id=f"cl_{tag}_s",
                    kind="list_item",
                    span_start=start,
                    span_end=start + len(word),
                    claim_text=word,
                    rule="test:enumeration",
                    cues=cues,
                    proposed_feature_id=feature,
                )
            )
        for index, (key, path, boilerplate) in enumerate(
            (("sym", ["Signs and symptoms"], False), ("lead", [], False), ("ref", ["References"], True))
        ):
            tx.add(
                EvidenceChunk(
                    chunk_id=f"ch_{tag}_{key}",
                    record_id=f"rec_{tag}_t",
                    knowledge_release_id=f"know-{tag}",
                    chunk_text=f"{PART} ({key})",
                    details={
                        "file": f"pretend_ache_{tag}.txt",
                        "disease_id": f"dis_{tag}",
                        "disease_label": f"pretend ache {tag}",
                        "section_path": path,
                        "char_start": index * 100,
                        "char_end": index * 100 + 80,
                        "source_url": "https://example.org/text",
                        "boilerplate": boilerplate,
                        "extraction_version": "test-1",
                    },
                )
            )
    return tag


def _decide(client, who: Api, target_type: str, target_id: str, status: str):
    body = {"target_type": target_type, "target_id": target_id, "note": "Decided in a test.", "status": status}
    return client.post(DECIDE, headers=who.headers(None), json=body)


def _notes(owner_db, target_id: str) -> list[tuple]:
    with owner_db.transaction(None, role="migration") as tx:
        rows = tx.execute(
            text(
                "SELECT target_type, status_change, reviewer, note FROM review_notes WHERE target_id = :t "
                "ORDER BY created_at, status_change"
            ),
            {"t": target_id},
        ).all()
    return [tuple(row) for row in rows]


def test_claims_are_listed_under_their_statement_for_reviewers_only(client, api: Api, reviewer: Api, world):
    tag = world

    def listed(who=reviewer, **params):
        return client.get(CLAIMS, params={"statement_id": f"st_{tag}", **params}, headers=who.headers(None))

    assert (listed(api).status_code, client.get(CHUNKS, headers=api.headers(None)).status_code) == (403, 403)
    body = listed().json()
    assert body["total"] == 1 and set(body["marks"]) == {"cut_off", "first_item_preposition"}
    statement = body["items"][0]
    assert (statement["statement_id"], statement["statement_type"], statement["text"], statement["has_a_mark"]) == (
        f"st_{tag}",
        "symptom",
        SENTENCE,
        True,
    )
    assert statement["disease"] == {"id": f"dis_{tag}", "term": f"pretend ache {tag}"}
    # One sentence, with the items of its list under it.
    (sentence,) = statement["claims"]
    assert (sentence["claim_id"], sentence["kind"], sentence["text"], sentence["span"]) == (
        f"cl_{tag}_s",
        "sentence",
        SENTENCE,
        [0, len(SENTENCE)],
    )
    hat, scarf = sentence["items"]
    assert (hat["text"], hat["marks"], hat["proposed_feature"], hat["review_status"], hat["applicability"]) == (
        "a pretend hat",
        ["first_item_preposition"],
        {"id": f"feat_{tag}", "term": f"hat {tag}"},
        "pending",
        None,
    )
    assert (scarf["text"], scarf["marks"], scarf["proposed_feature"]) == ("a scarf", [], None)
    # The filters choose statements: by a mark, by a proposed feature, by status.
    assert listed(mark="first_item_preposition").json()["total"] == 1
    assert listed(mark="cut_off").json()["total"] == 0 and listed(with_feature=True).json()["total"] == 1
    assert listed(status="approved").json()["total"] == 0
    assert (listed(mark="no such mark").status_code, listed(status="no such status").status_code) == (422, 422)


def test_an_approved_list_item_that_names_a_feature_becomes_evidence_once(
    client, api: Api, reviewer: Api, world, owner_db
):
    tag, signed = world, f"dev-reviewer:{reviewer.subject}"
    claim, made = f"cl_{tag}_hat", evidence_id_of(f"cl_{tag}_hat")

    def evidence():
        with owner_db.transaction(None, role="migration") as tx:
            rows = tx.scalars(
                select(DiseaseFeatureEvidence).where(DiseaseFeatureEvidence.statement_id == f"st_{tag}")
            ).all()
            return [(row.evidence_id, row.status) for row in rows]

    assert _decide(client, api, "claim", claim, "approved").status_code == 403
    # A sentence, and an item that names no feature, make nothing.
    assert _decide(client, reviewer, "claim", f"cl_{tag}_s", "approved").status_code == 200
    assert _decide(client, reviewer, "claim", f"cl_{tag}_scarf", "approved").status_code == 200
    assert evidence() == []
    assert _decide(client, reviewer, "claim", claim, "approved").status_code == 200
    assert evidence() == [(made, "approved")]
    with owner_db.transaction(None, role="migration") as tx:
        row = tx.get(DiseaseFeatureEvidence, made)
        stored = tx.get(StatementClaim, claim)
        assert (row.disease_id, row.feature_id, row.statement_id, row.record_id) == (
            f"dis_{tag}",
            f"feat_{tag}",
            f"st_{tag}",
            None,
        )
        assert (row.relationship, row.evidence_type) == ("listed_as_symptom_in_statement", "reviewed_claim")
        assert (row.context["claim_id"], row.context["claim_text"]) == (claim, "a pretend hat")
        assert (stored.status, stored.reviewer) == ("approved", signed)
    # The evidence row carries its own decision record, under the reviewer's name.
    assert _notes(owner_db, made) == [("evidence", "approved", signed, f"Made from the approved claim {claim}")]
    # Withdrawn, the evidence row is retired; approved again, it is the same row. Never a second one.
    assert _decide(client, reviewer, "claim", claim, "rejected").status_code == 200
    assert evidence() == [(made, "retired")]
    assert _decide(client, reviewer, "claim", claim, "approved").status_code == 200
    assert _decide(client, reviewer, "claim", claim, "approved").status_code == 200
    assert evidence() == [(made, "approved")]
    assert [note[1] for note in _notes(owner_db, made)].count("approved") == 2


def test_a_reviewer_says_in_words_for_whom_a_claim_holds(client, api: Api, reviewer: Api, world, owner_db):
    tag, signed = world, f"dev-reviewer:{reviewer.subject}"
    path = f"{CLAIMS}/cl_{tag}_hat/applicability"

    def put(who=reviewer, **body):
        return client.post(path, headers=who.headers(None), json={"note": "The sentence says so.", **body})

    assert put(api, text="adults").status_code == 403
    assert put(text="x" * 501).status_code == 422 and put(text="   ").status_code == 422
    missing = f"{CLAIMS}/cl_{tag}_none/applicability"
    assert client.post(missing, headers=reviewer.headers(None), json={"note": "n", "text": "x"}).status_code == 404
    answer = put(text="  in children  ")
    assert answer.status_code == 200
    recorded = answer.json()
    assert (recorded["applicability"]["text"], recorded["applicability"]["set_by"]) == ("in children", signed)
    assert recorded["review_status"] == "pending"  # saying for whom a claim holds decides nothing
    listed = client.get(CLAIMS, params={"statement_id": f"st_{tag}"}, headers=reviewer.headers(None)).json()
    assert listed["items"][0]["claims"][0]["items"][0]["applicability"]["text"] == "in children"
    assert _notes(owner_db, f"cl_{tag}_hat") == [("claim", None, signed, "The sentence says so.")]
    assert put(text=None).json()["applicability"] is None


def test_an_approved_part_of_a_text_becomes_a_statement_with_its_place_in_the_file(
    client, reviewer: Api, world, owner_db
):
    tag, signed = world, f"dev-reviewer:{reviewer.subject}"
    chunk, made = f"ch_{tag}_sym", statement_id_of(f"ch_{tag}_sym")
    listed = client.get(CHUNKS, params={"disease_id": f"dis_{tag}"}, headers=reviewer.headers(None)).json()
    assert listed["total"] == 3
    by_id = {item["chunk_id"].rsplit("_", 1)[1]: item for item in listed["items"]}
    # The type a part would get as a statement comes from the heading the source put it under.
    assert {key: item["statement_type_if_approved"] for key, item in by_id.items()} == {
        "sym": "symptom",
        "lead": "description",
        "ref": "description",
    }
    assert (by_id["ref"]["is_references_or_links"], by_id["sym"]["is_references_or_links"]) == (True, False)
    assert (by_id["sym"]["text"], by_id["sym"]["section_path"], by_id["sym"]["review_status"]) == (
        f"{PART} (sym)",
        ["Signs and symptoms"],
        "pending",
    )
    assert client.get(CHUNKS, params={"q": f"({tag}"}, headers=reviewer.headers(None)).json()["total"] == 0
    # A list of references is not a statement.
    refused = _decide(client, reviewer, "chunk", f"ch_{tag}_ref", "approved")
    assert (refused.status_code, refused.json()["code"]) == (409, "chunk_is_boilerplate")
    assert _decide(client, reviewer, "chunk", chunk, "approved").status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        statement = tx.get(Statement, made)
        source = tx.scalars(select(StatementSource).where(StatementSource.statement_id == made)).one()
        stored = tx.get(EvidenceChunk, chunk)
        assert (statement.text_content, statement.statement_type, statement.disease_id, statement.status) == (
            f"{PART} (sym)",
            "symptom",
            f"dis_{tag}",
            "approved",
        )
        assert statement.reviewed_by == signed and statement.reviewed_at is not None
        assert (source.record_id, source.source_url) == (f"rec_{tag}_t", "https://example.org/text")
        assert source.text_span == {
            "chunk_id": chunk,
            "file": f"pretend_ache_{tag}.txt",
            "char_start": 0,
            "char_end": 80,
            "section_path": ["Signs and symptoms"],
            "extraction_version": "test-1",
        }
        assert (stored.status, stored.reviewer, stored.statement_id) == ("approved", signed, made)
    assert _notes(owner_db, made) == [("statement", "approved", signed, f"Made from the approved chunk {chunk}")]
    # Withdrawn, the statement is retired; approved again, it is the same statement.
    assert _decide(client, reviewer, "chunk", chunk, "rejected").status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        assert tx.get(Statement, made).status == "retired"
    assert _decide(client, reviewer, "chunk", chunk, "approved").status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        assert tx.get(Statement, made).status == "approved"
        made_from_text = (
            select(func.count()).select_from(StatementSource).where(StatementSource.record_id == f"rec_{tag}_t")
        )
        assert tx.scalar(made_from_text) == 1


def test_what_the_approvals_made_enters_a_knowledge_release(client, reviewer: Api, world, owner_db):
    tag = world
    for target_type, target_id in (
        ("source", f"src_{tag}"),
        ("disease", f"dis_{tag}"),
        ("feature", f"feat_{tag}"),
        ("statement", f"st_{tag}"),
        ("claim", f"cl_{tag}_hat"),
        ("chunk", f"ch_{tag}_sym"),
    ):
        assert _decide(client, reviewer, target_type, target_id, "approved").status_code == 200, target_type
    for path, body in (
        ("/internal/v1/review/mapping-releases", {"mapping_release_id": f"map-{tag}"}),
        ("/internal/v1/review/knowledge-releases", {"knowledge_release_id": f"know-{tag}"}),
    ):
        assert client.post(path, headers=reviewer.headers(None), json={**body, "note": "Publish."}).status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        content = tx.get(PublishedKnowledge, f"know-{tag}.r1").content
    made = statement_id_of(f"ch_{tag}_sym")
    statements = {row["statement_id"]: row for row in content["statements"] if row["disease_id"] == f"dis_{tag}"}
    assert set(statements) == {f"st_{tag}", made}
    # The approved part of the text is in the release as its statement, with the chunk and its place in the file.
    span = statements[made]["sources"][0]["text_span"]
    assert (span["chunk_id"], span["file"], span["char_start"], span["char_end"]) == (
        f"ch_{tag}_sym",
        f"pretend_ache_{tag}.txt",
        0,
        80,
    )
    # The evidence row made from the approved claim is in it too, resting on its statement.
    evidence = [row for row in content["evidence"] if row["disease_id"] == f"dis_{tag}"]
    assert [(row["evidence_id"], row["feature_id"], row["statement_id"]) for row in evidence] == [
        (evidence_id_of(f"cl_{tag}_hat"), f"feat_{tag}", f"st_{tag}")
    ]


@pytest.mark.postgres
def test_claims_and_chunks_are_for_reviewers_only_in_the_database_too(client, reviewer: Api, world, db):
    tag = world
    one = {"c": f"cl_{tag}_hat", "k": f"ch_{tag}_sym", "s": f"st_{tag}", "d": f"dis_{tag}", "f": f"feat_{tag}"}
    # In a user's transaction the application role sees no claim and no chunk, and decides none.
    with db.transaction("someone") as tx:
        assert tx.execute(text("SELECT count(*) FROM statement_claims WHERE claim_id = :c"), one).scalar_one() == 0
        assert tx.execute(text("SELECT count(*) FROM evidence_chunks WHERE chunk_id = :k"), one).scalar_one() == 0
        changed = tx.execute(text("UPDATE statement_claims SET status = 'approved' WHERE claim_id = :c"), one)
        assert changed.rowcount == 0
    # Nor does it make evidence or a statement there.
    for statement in (
        "INSERT INTO disease_feature_evidence (evidence_id, disease_id, feature_id, statement_id, relationship, "
        "evidence_type) VALUES ('ev_x_' || :c, :d, :f, :s, 'sample', 'sample')",
        "INSERT INTO statements (statement_id, disease_id, statement_type, text_content) "
        "VALUES ('st_x_' || :c, :d, 'description', 'Words.')",
    ):
        with pytest.raises(DBAPIError), db.transaction("someone") as tx:
            tx.execute(text(statement), one)
    # A reviewer's transaction reads them, and cannot change the wording of a claim or of a chunk.
    with db.transaction("someone", role="reviewer") as tx:
        assert tx.execute(text("SELECT count(*) FROM statement_claims WHERE claim_id = :c"), one).scalar_one() == 1
    for statement in (
        "UPDATE statement_claims SET claim_text = 'other words' WHERE claim_id = :c",
        "UPDATE evidence_chunks SET chunk_text = 'other words' WHERE chunk_id = :k",
    ):
        with pytest.raises(DBAPIError), db.transaction("someone", role="reviewer") as tx:
            tx.execute(text(statement), one)
