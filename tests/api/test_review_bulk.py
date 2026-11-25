"""Many rows decided at once (M2.4j): each row is decided as a single decision is; one refusal changes nothing."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api import review_bulk
from feeltriva_api.auth import Principal
from feeltriva_api.errors import ApiError
from feeltriva_api.models import AuditEvent, Disease, ReviewNote, TerminologyLink
from sqlalchemy import select

from tests.conftest import Api

BULK = "/internal/v1/review/decisions/bulk"
ICD = "ICD-11 MMS"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def links(owner_db):
    """Three invented diseases with one link each, and a fourth with a general and a narrower candidate."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None) as tx:
        for key in ("a", "b", "c", "d"):
            tx.add(Disease(disease_id=f"dis_{tag}_{key}", preferred_name=f"pretend {key} {tag}"))
        tx.flush()
        for key, disease, code in (
            ("a", "a", f"WA{tag}"),
            ("b", "b", f"WB{tag}"),
            ("c", "c", f"WC{tag}"),
            ("general", "d", f"WD{tag}"),
            ("narrow", "d", f"WD{tag}.1"),
        ):
            tx.add(
                TerminologyLink(
                    link_id=f"tl_{tag}_{key}",
                    disease_id=f"dis_{tag}_{disease}",
                    system=ICD,
                    system_version="test",
                    code=code,
                    title=f"Pretend {key}",
                    uri=f"http://example.invalid/{code}",
                    match_method="exact_title",
                    detail={},
                )
            )
    return tag


def _statuses(owner_db, tag):
    with owner_db.transaction(None) as tx:
        rows = tx.scalars(select(TerminologyLink).where(TerminologyLink.link_id.like(f"tl_{tag}_%"))).all()
        return {row.link_id.rsplit("_", 1)[1]: (row.status, row.reviewer) for row in rows}


def _send(client, who: Api, tag: str, keys, status="approved", note="Decided together in a test."):
    body = {"target_type": "terminology_link", "target_ids": [f"tl_{tag}_{key}" for key in keys], "note": note}
    if status is not None:
        body["status"] = status
    return client.post(BULK, json=body, headers=who.headers(None))


def test_every_row_is_decided_as_a_single_decision_is_with_its_own_note_and_record(
    client, api: Api, reviewer: Api, links, owner_db
):
    assert client.post(BULK, json={}).status_code == 401
    assert _send(client, api, links, ["a"]).status_code == 403  # a signed-in user is not a reviewer
    done = _send(client, reviewer, links, ["a", "b", "c", "a"])  # a row named twice is decided once
    assert done.status_code == 200, done.text
    name = f"dev-reviewer:{reviewer.subject}"
    assert done.json() == {
        "target_type": "terminology_link",
        "review_status": "approved",
        "decided": 3,
        "refused": [],
        "reviewer": name,
    }
    assert {key: _statuses(owner_db, links)[key] for key in "abc"} == dict.fromkeys("abc", ("approved", name))
    ids = [f"tl_{links}_{key}" for key in "abc"]
    with owner_db.transaction(None) as tx:
        notes = tx.scalars(select(ReviewNote).where(ReviewNote.target_id.in_(ids))).all()
        audits = [
            event
            for event in tx.scalars(select(AuditEvent).where(AuditEvent.actor_subject == name)).all()
            if event.redacted_metadata.get("target_id") in ids
        ]
    assert sorted(note.target_id for note in notes) == sorted(ids)
    assert {(note.note, note.status_change, note.reviewer) for note in notes} == {
        ("Decided together in a test.", "approved", name)
    }
    assert sorted(event.redacted_metadata["target_id"] for event in audits) == sorted(ids)
    assert {(event.redacted_metadata["from"], event.redacted_metadata["to"]) for event in audits} == {
        ("pending", "approved")
    }
    # Undone together as well.
    assert _send(client, reviewer, links, ["a", "b"], status="pending").json()["decided"] == 2
    assert {key: _statuses(owner_db, links)[key][0] for key in "abc"} == {
        "a": "pending",
        "b": "pending",
        "c": "approved",
    }


def test_one_refused_row_changes_nothing_and_the_answer_names_it_with_the_reason(client, reviewer, links, owner_db):
    before = _statuses(owner_db, links)
    refused = _send(client, reviewer, links, ["a", "b", "narrow", "c"])
    assert refused.status_code == 409 and refused.json()["code"] == "general_term_is_default"
    message = refused.json()["message"]
    assert message.startswith(f"Nothing was changed. The row tl_{links}_narrow cannot take this decision: ")
    assert '"Pretend general"' in message and f"WD{links}" not in message  # a title and our own ID, never a code
    assert _statuses(owner_db, links) == before  # not even the rows before the refused one
    with owner_db.transaction(None) as tx:
        left = tx.scalars(select(ReviewNote).where(ReviewNote.target_id.like(f"tl_{links}_%"))).all()
    assert left == []


def test_what_is_not_a_bulk_decision_is_refused(client, reviewer, links):
    assert _send(client, reviewer, links, ["a"], status=None).status_code == 422  # a note alone is for one row
    assert _send(client, reviewer, links, ["a"], status="nonsense").status_code == 422
    assert _send(client, reviewer, links, []).status_code == 422
    too_many = {"target_type": "terminology_link", "target_ids": [f"x{n}" for n in range(201)], "note": "n"}
    assert client.post(BULK, json={**too_many, "status": "approved"}, headers=reviewer.headers(None)).status_code == 422
    unknown = {"target_type": "no_such_list", "target_ids": ["x"], "note": "n", "status": "approved"}
    assert client.post(BULK, json=unknown, headers=reviewer.headers(None)).json()["code"] == "unknown_review_target"
    missing = _send(client, reviewer, links, ["a", "nowhere"])
    assert missing.status_code == 404 and "Nothing was changed" in missing.json()["message"]


def test_each_row_on_its_own_decides_what_the_rules_allow_and_lists_what_they_refuse(container, links, owner_db):
    who = Principal(subject="dev-reviewer:each", roles=frozenset({"reviewer"}))
    ids = [f"tl_{links}_{key}" for key in ("a", "narrow", "general", "nowhere", "b")]
    result = review_bulk.decide_each(
        container.db, who, target_type="terminology_link", target_ids=ids, note="A whole list.", status="approved"
    )
    assert (result["decided"], result["reviewer"]) == (3, "dev-reviewer:each")
    assert [(row["target_id"].rsplit("_", 1)[1], row["code"]) for row in result["refused"]] == [
        ("narrow", "general_term_is_default"),
        ("nowhere", "review_target_not_found"),
    ]
    assert {key: status for key, (status, _who) in _statuses(owner_db, links).items()} == {
        "a": "approved",
        "b": "approved",
        "c": "pending",
        "general": "approved",
        "narrow": "pending",
    }
    with pytest.raises(ApiError, match="Unknown review status"):
        review_bulk.decide_each(
            container.db, who, target_type="terminology_link", target_ids=ids, note="n", status="nonsense"
        )
    with pytest.raises(ApiError):  # not a reviewer
        review_bulk.decide_each(
            container.db,
            Principal(subject="dev:someone", roles=frozenset()),
            target_type="terminology_link",
            target_ids=ids,
            note="n",
            status="approved",
        )


def test_the_sets_a_version_is_published_from_are_listed_for_reviewers_only(client, api: Api, reviewer: Api, owner_db):
    from feeltriva_api.models import KnowledgeRelease, MappingRelease, RuleBundle

    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(RuleBundle(bundle_id=f"ws-rules-{tag}", version=f"ws-rules-{tag}-1", manifest_uri="test://ws"))
        tx.add(MappingRelease(release_id=f"ws-names-{tag}", version=f"ws-names-{tag}-1"))
        tx.flush()
        tx.add(
            KnowledgeRelease(
                release_id=f"ws-know-{tag}",
                mapping_release_id=f"ws-names-{tag}",
                version=f"ws-know-{tag}-1",
                manifest_uri="test://ws",
            )
        )
    path = "/internal/v1/review/working-sets"
    assert client.get(path).status_code == 401 and client.get(path, headers=api.headers(None)).status_code == 403
    body = client.get(path, headers=reviewer.headers(None)).json()
    assert set(body) == {"rule_sets", "name_lists", "knowledge_sets"}
    for kind, wanted in (("rule_sets", "ws-rules"), ("name_lists", "ws-names"), ("knowledge_sets", "ws-know")):
        mine = [row for row in body[kind] if row["id"] == f"{wanted}-{tag}"]
        assert mine == [{"id": f"{wanted}-{tag}", "version": f"{wanted}-{tag}-1", "review_status": "pending"}]
        assert [row["id"] for row in body[kind]] == sorted(row["id"] for row in body[kind])


def test_follow_up_questions_and_sets_of_rules_are_listed_and_decided_like_any_other_row(
    client, api: Api, reviewer: Api, owner_db
):
    from feeltriva_api.models import Feature, FollowupQuestion, RuleBundle

    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(RuleBundle(bundle_id=f"aa-{tag}", version=f"aa-{tag}-1", manifest_uri="test://q"))
        tx.add(Feature(feature_id=f"feat_q_{tag}", preferred_name=f"hat {tag}", kind="symptom", value_type="boolean"))
        tx.flush()
        for key, about in (("one", f"feat_q_{tag}"), ("two", None)):
            tx.add(
                FollowupQuestion(
                    question_id=f"q.{tag}.{key}",
                    bundle_id=f"aa-{tag}",
                    feature_id=about,
                    wording=f"An invented question {key}?",
                    answer_schema={"type": "yes_no_unsure"},
                    applicability={},
                    branch_rules={},
                    evidence_ids=[],
                )
            )
    questions, sets = "/internal/v1/review/questions", "/internal/v1/review/rule-sets"
    for path in (questions, sets):
        assert client.get(path).status_code == 401 and client.get(path, headers=api.headers(None)).status_code == 403
    listed = client.get(questions, params={"limit": 200}, headers=reviewer.headers(None)).json()
    mine = [item for item in listed["items"] if item["bundle_id"] == f"aa-{tag}"]
    assert mine == [
        {
            "question_id": f"q.{tag}.one",
            "bundle_id": f"aa-{tag}",
            "wording": "An invented question one?",
            "answer_type": "yes_no_unsure",
            "asks_about": {"id": f"feat_q_{tag}", "term": f"hat {tag}"},
            "review_status": "pending",
        },
        {
            "question_id": f"q.{tag}.two",
            "bundle_id": f"aa-{tag}",
            "wording": "An invented question two?",
            "answer_type": "yes_no_unsure",
            "asks_about": None,
            "review_status": "pending",
        },
    ]
    assert client.get(questions, params={"status": "nonsense"}, headers=reviewer.headers(None)).status_code == 422
    decided = client.post(
        "/internal/v1/review/decisions",
        json={"target_type": "followup_question", "target_id": f"q.{tag}.one", "status": "approved", "note": "ok"},
        headers=reviewer.headers(None),
    )
    assert decided.status_code == 200
    approved = client.get(questions, params={"status": "approved", "limit": 200}, headers=reviewer.headers(None)).json()
    assert f"q.{tag}.one" in [item["question_id"] for item in approved["items"]]
    body = client.get(sets, headers=reviewer.headers(None)).json()
    assert body["total"] == len(body["items"])
    (mine_set,) = [item for item in body["items"] if item["bundle_id"] == f"aa-{tag}"]
    assert (mine_set["review_status"], mine_set["approved_by"], mine_set["rules_by_status"]) == ("pending", None, {})
