"""Evidence and sources as review targets, and the published knowledge release (M2.5c3). Invented rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from feeltriva_api import disease_merges, published_knowledge, published_mappings
from feeltriva_api.auth import Principal
from feeltriva_api.db import Database
from feeltriva_api.errors import ApiError
from feeltriva_api.models import (
    Base,
    Disease,
    DiseaseFeatureEvidence,
    Feature,
    KnowledgeRelease,
    MappingRelease,
    PublishedKnowledge,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from feeltriva_api.review import ReviewService
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

RELEASES = "/internal/v1/review/knowledge-releases"
MAPPINGS = "/internal/v1/review/mapping-releases"
DECIDE = "/internal/v1/review/decisions"
MERGE = "/internal/v1/review/disease-merges"
SOMEONE = Principal(subject="dev-reviewer:someone", roles=frozenset({"reviewer"}))


def _rows(db: Database, tag: str) -> None:
    """An invented knowledge set, everything pending.

    Two sources, of which the tests approve one. Three disease labels: one kept, one merged into it, one never
    approved. Seven statements and six evidence rows, one for each way of being published, held back or left out.
    """
    with db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"map-{tag}", version=f"map-{tag}-0"))
        tx.flush()
        tx.add(
            KnowledgeRelease(
                release_id=f"know-{tag}",
                mapping_release_id=f"map-{tag}",
                version=f"know-{tag}-0",
                manifest_uri=f"test://know-{tag}",
            )
        )
        for key, licence in (("ok", "Sample licence 1.0"), ("no", None)):
            tx.add(
                Source(
                    source_id=f"src_{tag}_{key}",
                    source_name=f"sample-{tag}-{key}.csv",
                    version="1",
                    origin_url="https://example.org/sample",
                    licence=licence,
                    sha256=f"sha-{tag}-{key}",
                )
            )
        tx.flush()
        for number, source in ((1, "ok"), (2, "no"), (3, "ok")):
            tx.add(
                SourceRecord(
                    record_id=f"rec_{tag}_{number}",
                    source_id=f"src_{tag}_{source}",
                    file_path="sample.csv",
                    row_number=number,
                    content_hash=f"hash-{tag}-{number}",
                    raw_object_uri=f"test://{tag}/{number}",
                )
            )
        for name in ("hat", "coat"):
            tx.add(
                Feature(
                    feature_id=f"feat_{tag}_{name}",
                    preferred_name=f"{name} {tag}",
                    kind="symptom",
                    value_type="boolean",
                )
            )
        for key, name in (("kept", "pretend ache"), ("alias", "ache, pretend"), ("other", "made-up itch")):
            tx.add(Disease(disease_id=f"dis_{tag}_{key}", preferred_name=f"{name} {tag}"))
        tx.flush()
        past = datetime.now(UTC) - timedelta(days=1)
        for key, disease, record, expires in (
            ("a", "kept", 1, None),  # published
            ("b", "alias", 1, None),  # published under the label it is merged into
            ("c", "kept", 2, None),  # its source is not approved
            ("d", "other", 1, None),  # its disease is not approved
            ("e", "kept", None, None),  # it has no source
            ("f", "kept", 1, past),  # it has expired
            ("g", "kept", 1, None),  # it stays pending
        ):
            tx.add(
                Statement(
                    statement_id=f"st_{tag}_{key}",
                    disease_id=f"dis_{tag}_{disease}",
                    statement_type="description",
                    text_content=f"A sample sentence {key} about a pretend ache ({tag}).",
                    expires_at=expires,
                )
            )
            tx.flush()
            if record is not None:
                tx.add(
                    StatementSource(
                        statement_id=f"st_{tag}_{key}",
                        record_id=f"rec_{tag}_{record}",
                        source_url="https://example.org/sample",
                        text_span={"column": "sample"},
                    )
                )
        for number, feature, statement, record in (
            (1, "hat", None, 3),  # published, from a record of the approved source
            (2, "hat", "a", None),  # published, resting on a published statement
            (3, "hat", "c", None),  # rests on a statement that is held back
            (4, "coat", None, 3),  # its feature is not approved
            (5, "hat", None, 2),  # its source is not approved
            (6, "hat", None, 3),  # it stays pending
        ):
            tx.add(
                DiseaseFeatureEvidence(
                    evidence_id=f"ev_{tag}_{number}",
                    disease_id=f"dis_{tag}_kept",
                    feature_id=f"feat_{tag}_{feature}",
                    statement_id=f"st_{tag}_{statement}" if statement else None,
                    record_id=f"rec_{tag}_{record}" if record else None,
                    relationship="sample_relation",
                    context={"sample": True},
                    frequency=0.25 if number == 1 else None,
                    frequency_denominator=40 if number == 1 else None,
                    evidence_type="sample",
                )
            )


def _decisions(tag: str) -> list[tuple[str, str]]:
    """Everything the tests approve: one source, one feature, one disease, six statements, five evidence rows."""
    return [
        ("source", f"src_{tag}_ok"),
        ("feature", f"feat_{tag}_hat"),
        ("disease", f"dis_{tag}_kept"),
        *[("statement", f"st_{tag}_{key}") for key in "abcdef"],
        *[("evidence", f"ev_{tag}_{number}") for number in range(1, 6)],
    ]


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def knowledge(owner_db) -> str:
    """The rows stay in the test database with the decisions the tests record on them through the review path.
    The self-check of `load-evidence`, whose tests share this database, accepts such rows since M2.5d1."""
    tag = uuid.uuid4().hex[:10]
    _rows(owner_db, tag)
    return tag


def _decide(client, who: Api, target_type: str, target_id: str, status: str = "approved"):
    body = {"target_type": target_type, "target_id": target_id, "note": "Decided in a test.", "status": status}
    return client.post(DECIDE, headers=who.headers(None), json=body)


def _approve_all(client, who: Api, tag: str) -> None:
    """Approve what the tests approve, merge the alias into the kept label and publish the mapping release."""
    for target_type, target_id in _decisions(tag):
        assert _decide(client, who, target_type, target_id).status_code == 200, (target_type, target_id)
    merge = {
        "source_disease_id": f"dis_{tag}_alias",
        "target_disease_id": f"dis_{tag}_kept",
        "note": "They name the same thing.",
    }
    assert client.post(MERGE, headers=who.headers(None), json=merge).status_code == 200
    body = {"mapping_release_id": f"map-{tag}", "note": "Publish in a test."}
    assert client.post(MAPPINGS, headers=who.headers(None), json=body).status_code == 200


def _publish(client, who: Api, tag: str):
    body = {"knowledge_release_id": f"know-{tag}", "note": "Publish in a test."}
    return client.post(RELEASES, headers=who.headers(None), json=body)


def _mine(items: list[dict], tag: str, key: str) -> list[dict]:
    """Only the invented rows of this test: the test database also holds the rows of other tests."""
    return [item for item in items if tag in item[key]]


def test_a_reviewer_decides_a_source_and_an_evidence_row_and_publishes_a_knowledge_release(
    client, api: Api, reviewer: Api, knowledge, owner_db
):
    tag = knowledge
    for path in ("/internal/v1/review/sources", "/internal/v1/review/evidence", RELEASES):
        assert client.get(path, headers=api.headers(None)).status_code == 403
    assert (_decide(client, api, "source", f"src_{tag}_ok").status_code, _publish(client, api, tag).status_code) == (
        403,
        403,
    )

    def sources():
        listed = client.get("/internal/v1/review/sources", headers=reviewer.headers(None)).json()["items"]
        return {item["source_id"]: item for item in _mine(listed, tag, "source_id")}

    def evidence(**params):
        params = {"disease_id": f"dis_{tag}_kept", **params}
        return client.get("/internal/v1/review/evidence", params=params, headers=reviewer.headers(None)).json()

    before = sources()[f"src_{tag}_ok"]
    assert (before["review_status"], before["licence"], before["decided_by"]) == ("pending", "Sample licence 1.0", None)
    assert evidence()["total"] == 6 and evidence(status="approved")["total"] == 0
    first = evidence(feature_id=f"feat_{tag}_hat", limit=1)["items"][0]
    assert (first["evidence_id"], first["disease"]["term"], first["feature"]["term"], first["frequency"]) == (
        f"ev_{tag}_1",
        f"pretend ache {tag}",
        f"hat {tag}",
        0.25,
    )
    _approve_all(client, reviewer, tag)
    signed = f"dev-reviewer:{reviewer.subject}"
    after = sources()
    assert (after[f"src_{tag}_ok"]["review_status"], after[f"src_{tag}_ok"]["decided_by"]) == ("approved", signed)
    assert after[f"src_{tag}_no"]["review_status"] == "pending" and evidence(status="approved")["total"] == 5
    preview = client.get(
        f"{RELEASES}/preview", params={"knowledge_release_id": f"know-{tag}"}, headers=reviewer.headers(None)
    ).json()
    assert (preview["publishable"], preview["problems"], preview["mapping_release"]) == (True, [], f"map-{tag}.r1")
    published = _publish(client, reviewer, tag)
    assert published.status_code == 200
    release = published.json()
    assert (release["release_id"], release["number"], release["is_current"], release["published_by"]) == (
        f"know-{tag}.r1",
        1,
        True,
        signed,
    )
    assert (release["mapping_release"], release["mapping_release_is_current"], release["sha256"]) == (
        f"map-{tag}.r1",
        True,
        preview["sha256"],
    )
    with owner_db.transaction(None, role="migration") as tx:
        content = tx.get(PublishedKnowledge, f"know-{tag}.r1").content
    # Of this test's seven statements and six evidence rows, two of each are in the release.
    assert [row["statement_id"] for row in _mine(content["statements"], tag, "statement_id")] == [
        f"st_{tag}_a",
        f"st_{tag}_b",
    ]
    assert [row["evidence_id"] for row in _mine(content["evidence"], tag, "evidence_id")] == [
        f"ev_{tag}_1",
        f"ev_{tag}_2",
    ]
    assert _mine(content["sources"], tag, "source_id") == [
        {
            "source_id": f"src_{tag}_ok",
            "source_name": f"sample-{tag}-ok.csv",
            "version": "1",
            "origin_url": "https://example.org/sample",
            "licence": "Sample licence 1.0",
            "permitted_uses": {},
            "sha256": f"sha-{tag}-ok",
        }
    ]
    again = _publish(client, reviewer, tag)
    assert (again.status_code, again.json()["code"]) == (409, "release_already_published")
    unknown = {"knowledge_release_id": "none", "note": "Publish in a test."}
    assert client.post(RELEASES, headers=reviewer.headers(None), json=unknown).status_code == 404


def test_what_a_knowledge_release_holds_what_it_holds_back_and_when_it_is_refused():
    """On a database of its own, so that every count is exact and nothing another test approved is in it."""
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine)
    tag = "own"
    _rows(db, tag)

    def outlook():
        return published_knowledge.preview(db, SOMEONE, f"know-{tag}")

    # Nothing decided, no mapping release.
    assert outlook()["problems"] == ["no mapping release is current", "no statement and no evidence is approved"]
    review = ReviewService(db)
    for target_type, target_id in _decisions(tag):
        review.record_review(SOMEONE, target_type=target_type, target_id=target_id, note="Decided.", status="approved")
    disease_merges.merge(db, SOMEONE, source_id=f"dis_{tag}_alias", target_id=f"dis_{tag}_kept", note="The same.")
    # Decided, but no mapping release is current: nothing has a disease to stand under.
    waiting = outlook()
    assert (waiting["publishable"], waiting["mapping_release"]) == (False, None)
    assert waiting["problems"] == [
        "no mapping release is current",
        "every approved statement and evidence row is held back",
    ]
    with pytest.raises(ApiError) as refused:
        published_knowledge.publish(db, SOMEONE, knowledge_release_id=f"know-{tag}", note="Publish.")
    assert (refused.value.status, refused.value.code) == (409, "release_not_publishable")
    mapping = published_mappings.publish(db, SOMEONE, mapping_release_id=f"map-{tag}", note="Publish.")
    ready = outlook()
    assert (ready["publishable"], ready["problems"], ready["mapping_release"]) == (True, [], f"map-{tag}.r1")
    assert (ready["statements"], ready["evidence"], ready["sources"]) == (2, 2, 1)
    assert ready["held_back"] == {
        "statements_expired": 1,
        "statements_without_source": 1,
        "statements_source_not_approved": 1,
        "statements_disease_not_in_mapping_release": 1,
        "evidence_disease_or_feature_not_in_mapping_release": 1,
        "evidence_statement_not_in_release": 1,
        "evidence_source_not_approved": 1,
    }
    assert ready["unresolved"] == {"statements": 1, "evidence": 1, "sources": 1}
    release = published_knowledge.publish(db, SOMEONE, knowledge_release_id=f"know-{tag}", note="Publish.")
    assert (release["release_id"], release["mapping_release"], release["mapping_release_is_current"]) == (
        f"know-{tag}.r1",
        f"map-{tag}.r1",
        True,
    )
    with db.transaction(None, role="migration") as tx:
        content = tx.get(PublishedKnowledge, f"know-{tag}.r1").content
    assert content["mapping_release"] == {"release_id": f"map-{tag}.r1", "sha256": mapping["sha256"]}
    source = {
        "record_id": f"rec_{tag}_1",
        "source_id": f"src_{tag}_ok",
        "source_url": "https://example.org/sample",
        "text_span": {"column": "sample"},
    }
    # A statement of a merged label keeps its own label and says which label it stands under.
    assert [
        (row["statement_id"], row["disease_id"], row["resolves_to"], row["text"], row["reviewed_by"], row["sources"])
        for row in content["statements"]
    ] == [
        (
            f"st_{tag}_a",
            f"dis_{tag}_kept",
            f"dis_{tag}_kept",
            f"A sample sentence a about a pretend ache ({tag}).",
            "dev-reviewer:someone",
            [source],
        ),
        (
            f"st_{tag}_b",
            f"dis_{tag}_alias",
            f"dis_{tag}_kept",
            f"A sample sentence b about a pretend ache ({tag}).",
            "dev-reviewer:someone",
            [source],
        ),
    ]
    assert content["evidence"] == [
        {
            "evidence_id": f"ev_{tag}_1",
            "disease_id": f"dis_{tag}_kept",
            "resolves_to": f"dis_{tag}_kept",
            "feature_id": f"feat_{tag}_hat",
            "relationship": "sample_relation",
            "evidence_type": "sample",
            "context": {"sample": True},
            "frequency": 0.25,
            "frequency_denominator": 40,
            "statement_id": None,
            "record_id": f"rec_{tag}_3",
            "source_id": f"src_{tag}_ok",
        },
        {
            "evidence_id": f"ev_{tag}_2",
            "disease_id": f"dis_{tag}_kept",
            "resolves_to": f"dis_{tag}_kept",
            "feature_id": f"feat_{tag}_hat",
            "relationship": "sample_relation",
            "evidence_type": "sample",
            "context": {"sample": True},
            "frequency": None,
            "frequency_denominator": None,
            "statement_id": f"st_{tag}_a",
            "record_id": None,
            "source_id": None,
        },
    ]
    with pytest.raises(ApiError) as twice:
        published_knowledge.publish(db, SOMEONE, knowledge_release_id=f"know-{tag}", note="Publish.")
    assert twice.value.code == "release_already_published"
    # Another mapping working set publishes and becomes current: this knowledge set names the first one, so it
    # can no longer be published, and its release says that its mapping release is not the current one.
    with db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id="map-second", version="map-second-0"))
    published_mappings.publish(db, SOMEONE, mapping_release_id="map-second", note="Publish.")
    review.record_review(SOMEONE, target_type="statement", target_id=f"st_{tag}_g", note="Decided.", status="approved")
    assert outlook()["problems"] == [
        f"the current mapping release map-second.r1 is not of the mapping working set map-{tag} this knowledge set names"
    ]
    listed = published_knowledge.list_published(db, SOMEONE)["items"]
    assert [(item["release_id"], item["mapping_release_is_current"]) for item in listed] == [(f"know-{tag}.r1", False)]
    with pytest.raises(ApiError) as forbidden:
        published_knowledge.publish(db, Principal(subject="dev:user"), knowledge_release_id=f"know-{tag}", note="No.")
    assert forbidden.value.status == 403


def test_a_rollback_makes_an_earlier_knowledge_release_current_and_removes_nothing(
    client, reviewer: Api, knowledge, owner_db
):
    tag = knowledge
    _approve_all(client, reviewer, tag)
    assert _publish(client, reviewer, tag).status_code == 200
    assert _decide(client, reviewer, "statement", f"st_{tag}_g").status_code == 200
    second = _publish(client, reviewer, tag)
    assert second.status_code == 200 and (second.json()["number"], second.json()["is_current"]) == (2, True)

    def mine():
        return {
            item["release_id"]: item["is_current"]
            for item in client.get(RELEASES, headers=reviewer.headers(None)).json()["items"]
            if item["knowledge_release_id"] == f"know-{tag}"
        }

    def held(release_id):
        with owner_db.transaction(None, role="migration") as tx:
            statements = tx.get(PublishedKnowledge, release_id).content["statements"]
        return [row["statement_id"][-1] for row in _mine(statements, tag, "statement_id")]

    assert mine() == {f"know-{tag}.r1": False, f"know-{tag}.r2": True}
    # The first release still holds what it held: publishing the second changed nothing in it.
    assert (held(f"know-{tag}.r1"), held(f"know-{tag}.r2")) == (["a", "b"], ["a", "b", "g"])

    def switch(release_id):
        body = {"release_id": release_id, "note": "Roll back."}
        return client.post(f"{RELEASES}/current", headers=reviewer.headers(None), json=body)

    back = switch(f"know-{tag}.r1")
    assert back.status_code == 200 and back.json()["is_current"] is True
    assert mine() == {f"know-{tag}.r1": True, f"know-{tag}.r2": False}
    assert held(f"know-{tag}.r2") == ["a", "b", "g"]
    assert (switch(f"know-{tag}.r1").status_code, switch(f"know-{tag}.r9").status_code) == (409, 404)
    with owner_db.transaction(None, role="migration") as tx:
        notes = tx.execute(
            text(
                "SELECT target_type, target_id, status_change, reviewer FROM review_notes "
                "WHERE target_id LIKE :t ORDER BY created_at"
            ),
            {"t": f"know-{tag}.r%"},
        ).all()
    signed = f"dev-reviewer:{reviewer.subject}"
    assert [tuple(row) for row in notes] == [
        ("knowledge_release", f"know-{tag}.r1", "published", signed),
        ("knowledge_release", f"know-{tag}.r2", "published", signed),
        ("knowledge_release", f"know-{tag}.r1", "made_current", signed),
    ]


@pytest.mark.postgres
def test_the_database_refuses_to_edit_or_delete_a_knowledge_release_and_lets_only_a_reviewer_decide_and_publish(
    client, reviewer: Api, knowledge, db, owner_db
):
    tag = knowledge
    _approve_all(client, reviewer, tag)
    assert _publish(client, reviewer, tag).status_code == 200
    release = {"r": f"know-{tag}.r1"}
    # Even the owner of the schema cannot edit or delete a published release.
    for statement, message in (
        ("UPDATE published_knowledge SET content = '{}'::jsonb WHERE release_id = :r", "cannot be edited"),
        ("UPDATE published_knowledge SET sha256 = 'x' WHERE release_id = :r", "cannot be edited"),
        ("UPDATE published_knowledge SET published_by = 'someone else' WHERE release_id = :r", "cannot be edited"),
        ("DELETE FROM published_knowledge WHERE release_id = :r", "cannot be deleted"),
    ):
        with pytest.raises(DBAPIError, match=message), owner_db.transaction(None, role="migration") as tx:
            tx.execute(text(statement), release)
    # Outside a reviewer's transaction the application role can neither publish nor change which release is current.
    with db.transaction("someone") as tx:
        switched = tx.execute(text("UPDATE published_knowledge SET is_current = false WHERE release_id = :r"), release)
        assert switched.rowcount == 0
    with pytest.raises(DBAPIError), db.transaction("someone") as tx:
        tx.execute(
            text(
                "INSERT INTO published_knowledge "
                "(release_id, knowledge_release_id, mapping_release, number, content, sha256, published_by) "
                "VALUES (:i, :w, :m, 99, '{}'::jsonb, 'x', 'someone')"
            ),
            {"i": f"know-{tag}.r99", "w": f"know-{tag}", "m": f"map-{tag}.r1"},
        )
    # Nor can it decide a source or an evidence row there; and in no transaction can it change a source's licence
    # or what an evidence row says.
    rows = {"s": f"src_{tag}_no", "e": f"ev_{tag}_6"}
    with db.transaction("someone") as tx:
        source = tx.execute(text("UPDATE sources SET provenance_status = 'approved' WHERE source_id = :s"), rows)
        row = tx.execute(text("UPDATE disease_feature_evidence SET status = 'approved' WHERE evidence_id = :e"), rows)
        assert (source.rowcount, row.rowcount) == (0, 0)
    for statement in (
        "UPDATE sources SET licence = 'another licence' WHERE source_id = :s",
        "UPDATE disease_feature_evidence SET relationship = 'another relation' WHERE evidence_id = :e",
    ):
        with pytest.raises(DBAPIError), db.transaction("someone", role="reviewer") as tx:
            tx.execute(text(statement), rows)
