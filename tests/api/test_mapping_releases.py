"""Features and diseases as review targets, and the published mapping release (M2.5c2). Invented rows."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api import published_mappings
from feeltriva_api.auth import Principal
from feeltriva_api.db import Database
from feeltriva_api.errors import ApiError
from feeltriva_api.models import (
    Base,
    Disease,
    DiseaseMapping,
    Feature,
    FeatureMapping,
    MappingRelease,
    PublishedMapping,
    Source,
)
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

RELEASES = "/internal/v1/review/mapping-releases"
DECIDE = "/internal/v1/review/decisions"
MERGE = "/internal/v1/review/disease-merges"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def vocabulary(owner_db) -> str:
    """An invented working set: one source, three features, three disease labels and their mappings, all pending."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"map-{tag}", version=f"map-{tag}-0"))
        tx.add(Source(source_id=f"src_{tag}", source_name=f"sample-{tag}.csv", version="1", sha256=f"sha-{tag}"))
        for name in ("hat", "scarf", "coat"):
            tx.add(
                Feature(
                    feature_id=f"feat_{tag}_{name}",
                    preferred_name=f"{name} {tag}",
                    kind="symptom",
                    value_type="boolean",
                    aliases=[f"{name}_{tag}"],
                )
            )
        for key, name in (("kept", "pretend ache"), ("alias", "ache, pretend"), ("other", "made-up itch")):
            tx.add(Disease(disease_id=f"dis_{tag}_{key}", preferred_name=f"{name} {tag}"))
        tx.flush()
        for key, label in (("kept", "Pretend ache"), ("alias", "Ache, pretend"), ("other", "Made-up itch")):
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{key}",
                    release_id=f"map-{tag}",
                    source_id=f"src_{tag}",
                    original_label=label,
                    original_id=f"row-{key}",
                    disease_id=f"dis_{tag}_{key}",
                    method="sample",
                )
            )
        for column, name in enumerate(("hat", "scarf", "coat"), start=1):
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{name}",
                    release_id=f"map-{tag}",
                    source_id=f"src_{tag}",
                    file_path="sample.csv",
                    column_index=column,
                    original_term=name.upper(),
                    feature_id=f"feat_{tag}_{name}",
                    zero_semantics="not_recorded",
                    transformation={
                        "meaning": {"kind": "symptom", "zero": "not_recorded", "status": "proposal, pending review"},
                        "audit_status": "needs_semantic_review",
                        "repeated_header": name == "hat",
                    },
                )
            )
    return tag


def _decide(client, who: Api, target_type: str, target_id: str, status: str):
    body = {"target_type": target_type, "target_id": target_id, "note": "Decided in a test.", "status": status}
    return client.post(DECIDE, headers=who.headers(None), json=body)


def _preview(client, who: Api, tag: str):
    return client.get(f"{RELEASES}/preview", params={"mapping_release_id": f"map-{tag}"}, headers=who.headers(None))


def _publish(client, who: Api, tag: str):
    body = {"mapping_release_id": f"map-{tag}", "note": "Publish in a test."}
    return client.post(RELEASES, headers=who.headers(None), json=body)


def _mine(items: list[dict], tag: str, key: str) -> list[dict]:
    """Only the invented rows of this test: the test database also holds the rows of other tests."""
    return [item for item in items if tag in item[key]]


def test_a_reviewer_decides_a_feature_and_a_disease_and_a_merged_label_is_not_decided(
    client, api: Api, reviewer: Api, vocabulary
):
    tag = vocabulary
    hat, kept, alias = f"feat_{tag}_hat", f"dis_{tag}_kept", f"dis_{tag}_alias"

    def features(who=reviewer, **params):
        return client.get("/internal/v1/review/features", params={"q": tag, **params}, headers=who.headers(None))

    def diseases(who=reviewer, **params):
        return client.get("/internal/v1/review/diseases", params={"q": tag, **params}, headers=who.headers(None))

    assert (features(api).status_code, diseases(api).status_code) == (403, 403)
    assert _decide(client, api, "feature", hat, "approved").status_code == 403
    listed = features().json()
    assert listed["total"] == 3 and {item["review_status"] for item in listed["items"]} == {"pending"}
    assert listed["items"][0]["decided_by"] is None and features(status="no such status").status_code == 422
    decided = _decide(client, reviewer, "feature", hat, "approved")
    assert decided.status_code == 200
    assert (decided.json()["previous_status"], decided.json()["review_status"]) == ("pending", "approved")
    assert _decide(client, reviewer, "feature", f"feat_{tag}_scarf", "rejected").status_code == 200
    assert _decide(client, reviewer, "feature", f"feat_{tag}_none", "approved").status_code == 404
    approved = features(status="approved").json()
    assert [(item["feature_id"], item["name"], item["kind"], item["other_names"]) for item in approved["items"]] == [
        (hat, f"hat {tag}", "symptom", [f"hat_{tag}"])
    ]
    signed = f"dev-reviewer:{reviewer.subject}"
    assert (approved["items"][0]["decided_by"], approved["items"][0]["decision_note"]) == (signed, "Decided in a test.")
    # A disease label is decided the same way.
    assert _decide(client, reviewer, "disease", kept, "approved").status_code == 200
    assert [item["disease_id"] for item in diseases(status="approved").json()["items"]] == [kept]
    # A label merged into another is not decided: the kept label is, or the merged one is split out first.
    merge = {"source_disease_id": alias, "target_disease_id": kept, "note": "They name the same thing."}
    assert client.post(MERGE, headers=reviewer.headers(None), json=merge).status_code == 200
    refused = _decide(client, reviewer, "disease", alias, "approved")
    assert (refused.status_code, refused.json()["code"]) == (409, "disease_is_merged")
    merged = {item["disease_id"]: item for item in diseases().json()["items"]}
    assert (merged[alias]["merged_into"], merged[alias]["review_status"]) == (kept, "retired")


def test_a_mapping_release_holds_only_what_is_approved(client, api: Api, reviewer: Api, vocabulary, owner_db):
    tag = vocabulary
    kept, alias = f"dis_{tag}_kept", f"dis_{tag}_alias"
    before = _preview(client, reviewer, tag).json()
    assert (before["disease_mappings"], before["feature_mappings"], before["would_be_number"]) == (0, 0, 1)
    assert before["unresolved"]["disease_mappings"] == 3 and before["unresolved"]["feature_mappings"] == 3
    # Two features approved and one rejected; one disease approved, one merged into it with the standard name
    # given to the kept label, one left pending.
    for name, status in (("hat", "approved"), ("coat", "approved"), ("scarf", "rejected")):
        assert _decide(client, reviewer, "feature", f"feat_{tag}_{name}", status).status_code == 200
    assert _decide(client, reviewer, "disease", kept, "approved").status_code == 200
    merge = {
        "source_disease_id": alias,
        "target_disease_id": kept,
        "note": "They name the same thing.",
        "kept_name": f"pretend ache syndrome {tag}",
    }
    assert client.post(MERGE, headers=reviewer.headers(None), json=merge).status_code == 200
    # Every disease mapping approved, also the one whose disease is still pending; the feature mappings of the
    # approved hat and the rejected scarf approved, the one of the coat left pending.
    for key in ("kept", "alias", "other"):
        assert _decide(client, reviewer, "disease_mapping", f"dm_{tag}_{key}", "approved").status_code == 200
    for name in ("hat", "scarf"):
        assert _decide(client, reviewer, "feature_mapping", f"fm_{tag}_{name}", "approved").status_code == 200
    ready = _preview(client, reviewer, tag).json()
    assert ready["publishable"] is True and ready["problems"] == []
    assert (ready["features"] - before["features"], ready["diseases"] - before["diseases"]) == (2, 1)
    assert (ready["disease_mappings"], ready["feature_mappings"], ready["sources"]) == (2, 1, 1)
    # An approved mapping whose disease or feature is not approved is held back, and counted.
    assert ready["held_back"] == {"disease_mappings": 1, "feature_mappings": 1}
    assert (ready["unresolved"]["disease_mappings"], ready["unresolved"]["feature_mappings"]) == (0, 1)
    assert (client.get(RELEASES, headers=api.headers(None)).status_code, _publish(client, api, tag).status_code) == (
        403,
        403,
    )
    published = _publish(client, reviewer, tag)
    assert published.status_code == 200
    release = published.json()
    assert (release["release_id"], release["number"], release["is_current"], release["published_by"]) == (
        f"map-{tag}.r1",
        1,
        True,
        f"dev-reviewer:{reviewer.subject}",
    )
    assert (release["sha256"], release["mapping_release_id"]) == (ready["sha256"], f"map-{tag}")
    with owner_db.transaction(None, role="migration") as tx:
        content = tx.get(PublishedMapping, f"map-{tag}.r1").content
    assert set(content) == {
        "mapping_release_id",
        "version",
        "features",
        "diseases",
        "redirects",
        "disease_mappings",
        "feature_mappings",
        "sources",
        "unresolved",
        "held_back",
    }
    # The rejected feature and the pending disease are not in the release.
    assert _mine(content["features"], tag, "feature_id") == [
        {
            "feature_id": f"feat_{tag}_{name}",
            "preferred_name": f"{name} {tag}",
            "kind": "symptom",
            "value_type": "boolean",
            "unit": None,
            "aliases": [f"{name}_{tag}"],
        }
        for name in ("coat", "hat")
    ]
    # The kept label carries its standard name; the merged label and the former name are its synonyms. A disease
    # entry has these fields and no other: no code of an outside vocabulary is in a release.
    assert _mine(content["diseases"], tag, "disease_id") == [
        {
            "disease_id": kept,
            "preferred_name": f"pretend ache syndrome {tag}",
            "definition": None,
            "synonyms": [f"ache, pretend {tag}", f"pretend ache {tag}"],
            "merged_labels": [alias],
        }
    ]
    history = client.get(f"/internal/v1/review/diseases/{kept}/history", headers=reviewer.headers(None)).json()
    assert history["synonyms"] == [f"ache, pretend {tag}", f"pretend ache {tag}"]
    assert content["redirects"][alias] == kept
    # The mapping of the merged label keeps its own label and says which label it resolves to.
    assert content["disease_mappings"] == [
        {
            "mapping_id": f"dm_{tag}_alias",
            "source_id": f"src_{tag}",
            "original_label": "Ache, pretend",
            "original_id": "row-alias",
            "disease_id": alias,
            "resolves_to": kept,
            "method": "sample",
        },
        {
            "mapping_id": f"dm_{tag}_kept",
            "source_id": f"src_{tag}",
            "original_label": "Pretend ache",
            "original_id": "row-kept",
            "disease_id": kept,
            "resolves_to": kept,
            "method": "sample",
        },
    ]
    # The stored notes that said "pending" are left out of an approved mapping; everything else is kept.
    assert content["feature_mappings"] == [
        {
            "mapping_id": f"fm_{tag}_hat",
            "source_id": f"src_{tag}",
            "file_path": "sample.csv",
            "column_index": 1,
            "original_term": "HAT",
            "feature_id": f"feat_{tag}_hat",
            "zero_semantics": "not_recorded",
            "details": {"meaning": {"kind": "symptom", "zero": "not_recorded"}, "repeated_header": True},
        }
    ]
    assert content["sources"] == [
        {"source_id": f"src_{tag}", "source_name": f"sample-{tag}.csv", "version": "1", "sha256": f"sha-{tag}"}
    ]
    # The same content cannot be published twice.
    again = _publish(client, reviewer, tag)
    assert (again.status_code, again.json()["code"]) == (409, "release_already_published")
    assert _preview(client, reviewer, tag).json()["same_as_release"] == f"map-{tag}.r1"
    assert _preview(client, reviewer, "none").status_code == 404


def test_nothing_is_published_while_no_feature_and_no_disease_is_approved():
    """On a database of its own, so that nothing another test approved is in it."""
    empty = Database("sqlite://")
    Base.metadata.create_all(empty.engine)
    who = Principal(subject="dev-reviewer:someone", roles=frozenset({"reviewer"}))
    with empty.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id="map-empty", version="map-empty-0"))
        tx.add(
            Feature(feature_id="feat_pending", preferred_name="a pending sample", kind="symptom", value_type="boolean")
        )
        tx.add(Disease(disease_id="dis_pending", preferred_name="a pending sample"))
    outlook = published_mappings.preview(empty, who, "map-empty")
    assert (outlook["publishable"], outlook["problems"]) == (False, ["no feature and no disease is approved"])
    assert outlook["unresolved"] == {"features": 1, "diseases": 1, "disease_mappings": 0, "feature_mappings": 0}
    with pytest.raises(ApiError) as refused:
        published_mappings.publish(empty, who, mapping_release_id="map-empty", note="Publish in a test.")
    assert (refused.value.status, refused.value.code) == (409, "release_not_publishable")
    assert "no feature and no disease is approved" in refused.value.message
    with empty.transaction(None, role="migration") as tx:
        assert tx.scalars(select(PublishedMapping)).all() == []
    with pytest.raises(ApiError) as forbidden:
        published_mappings.publish(empty, Principal(subject="dev:user"), mapping_release_id="map-empty", note="No.")
    assert forbidden.value.status == 403


def test_a_rollback_makes_an_earlier_mapping_release_current_and_removes_nothing(
    client, reviewer: Api, vocabulary, owner_db
):
    tag = vocabulary
    assert _decide(client, reviewer, "feature", f"feat_{tag}_hat", "approved").status_code == 200
    assert _publish(client, reviewer, tag).status_code == 200
    assert _decide(client, reviewer, "feature", f"feat_{tag}_coat", "approved").status_code == 200
    second = _publish(client, reviewer, tag)
    assert second.status_code == 200 and (second.json()["number"], second.json()["is_current"]) == (2, True)

    def mine():
        return {
            item["release_id"]: item["is_current"]
            for item in client.get(RELEASES, headers=reviewer.headers(None)).json()["items"]
            if item["mapping_release_id"] == f"map-{tag}"
        }

    def held(release_id):
        with owner_db.transaction(None, role="migration") as tx:
            features = tx.get(PublishedMapping, release_id).content["features"]
        return [feature["feature_id"] for feature in _mine(features, tag, "feature_id")]

    assert mine() == {f"map-{tag}.r1": False, f"map-{tag}.r2": True}
    # The first release still holds what it held: publishing the second changed nothing in it.
    assert held(f"map-{tag}.r1") == [f"feat_{tag}_hat"]
    assert held(f"map-{tag}.r2") == [f"feat_{tag}_coat", f"feat_{tag}_hat"]

    def switch(release_id):
        body = {"release_id": release_id, "note": "Roll back."}
        return client.post(f"{RELEASES}/current", headers=reviewer.headers(None), json=body)

    back = switch(f"map-{tag}.r1")
    assert back.status_code == 200 and back.json()["is_current"] is True
    assert mine() == {f"map-{tag}.r1": True, f"map-{tag}.r2": False}
    assert held(f"map-{tag}.r2") == [f"feat_{tag}_coat", f"feat_{tag}_hat"]
    assert (switch(f"map-{tag}.r1").status_code, switch(f"map-{tag}.r9").status_code) == (409, 404)
    with owner_db.transaction(None, role="migration") as tx:
        notes = tx.execute(
            text(
                "SELECT target_type, target_id, status_change, reviewer FROM review_notes "
                "WHERE target_id LIKE :t ORDER BY created_at"
            ),
            {"t": f"map-{tag}.r%"},
        ).all()
    signed = f"dev-reviewer:{reviewer.subject}"
    assert [tuple(row) for row in notes] == [
        ("mapping_release", f"map-{tag}.r1", "published", signed),
        ("mapping_release", f"map-{tag}.r2", "published", signed),
        ("mapping_release", f"map-{tag}.r1", "made_current", signed),
    ]


@pytest.mark.postgres
def test_the_database_refuses_to_edit_or_delete_a_mapping_release_and_lets_only_a_reviewer_decide_and_publish(
    client, reviewer: Api, vocabulary, db, owner_db
):
    tag = vocabulary
    assert _decide(client, reviewer, "feature", f"feat_{tag}_hat", "approved").status_code == 200
    assert _publish(client, reviewer, tag).status_code == 200
    release = {"r": f"map-{tag}.r1"}
    # Even the owner of the schema cannot edit or delete a published release.
    for statement, message in (
        ("UPDATE published_mappings SET content = '{}'::jsonb WHERE release_id = :r", "cannot be edited"),
        ("UPDATE published_mappings SET sha256 = 'x' WHERE release_id = :r", "cannot be edited"),
        ("UPDATE published_mappings SET published_by = 'someone else' WHERE release_id = :r", "cannot be edited"),
        ("DELETE FROM published_mappings WHERE release_id = :r", "cannot be deleted"),
    ):
        with pytest.raises(DBAPIError, match=message), owner_db.transaction(None, role="migration") as tx:
            tx.execute(text(statement), release)
    # Outside a reviewer's transaction the application role can neither publish nor change which release is current.
    with db.transaction("someone") as tx:
        switched = tx.execute(text("UPDATE published_mappings SET is_current = false WHERE release_id = :r"), release)
        assert switched.rowcount == 0
    with pytest.raises(DBAPIError), db.transaction("someone") as tx:
        tx.execute(
            text(
                "INSERT INTO published_mappings (release_id, mapping_release_id, number, content, sha256, published_by) "
                "VALUES (:i, :w, 99, '{}'::jsonb, 'x', 'someone')"
            ),
            {"i": f"map-{tag}.r99", "w": f"map-{tag}"},
        )
    # Nor can it decide a feature there; and in no transaction can it change a feature's name.
    feature = {"f": f"feat_{tag}_coat"}
    with db.transaction("someone") as tx:
        decided = tx.execute(text("UPDATE features SET status = 'approved' WHERE feature_id = :f"), feature)
        assert decided.rowcount == 0
    with pytest.raises(DBAPIError), db.transaction("someone", role="reviewer") as tx:
        tx.execute(text("UPDATE features SET preferred_name = 'another name' WHERE feature_id = :f"), feature)
    with db.transaction("someone") as tx:
        assert tx.execute(text("SELECT status FROM features WHERE feature_id = :f"), feature).scalar_one() == "pending"
