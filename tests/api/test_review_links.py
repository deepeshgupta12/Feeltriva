"""Vocabulary links in the review path (M2.17): reviewers only, a decision recorded with the reviewer, codes never for users."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api.models import Disease, Feature, TerminologyLink
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

PATH = "/internal/v1/review/terminology-links"
DECIDE = "/internal/v1/review/decisions"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def links(owner_db):
    """One invented disease with a general and a narrower candidate code, and one invented symptom with one link."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None) as tx:
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend ache {tag}"))
        tx.add(
            Feature(
                feature_id=f"feat_{tag}", preferred_name=f"pretend itch {tag}", kind="symptom", value_type="boolean"
            )
        )
        tx.flush()
        for key, disease, feature, system, code, title, method in (
            ("general", f"dis_{tag}", None, "ICD-11 MMS", f"ZZ{tag}", "Pretend ache", "mondo_equivalent"),
            (
                "narrow",
                f"dis_{tag}",
                None,
                "ICD-11 MMS",
                f"ZZ{tag}.0",
                "Pretend ache of the left side",
                "exact_synonym",
            ),
            ("symptom", None, f"feat_{tag}", "HPO", f"HP:{tag}", "Pretend itch", "exact_label"),
        ):
            tx.add(
                TerminologyLink(
                    link_id=f"tl_{tag}_{key}",
                    disease_id=disease,
                    feature_id=feature,
                    system=system,
                    system_version="test",
                    code=code,
                    title=title,
                    uri=f"http://example.invalid/{code}",
                    match_method=method,
                    detail={"query": title.lower()},
                )
            )
    return tag


def test_links_are_listed_for_reviewers_only_with_our_term_and_can_be_filtered(client, api: Api, reviewer: Api, links):
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=api.headers(None)).status_code == 403  # a signed-in user is not a reviewer
    body = client.get(PATH, params={"q": links}, headers=reviewer.headers(None)).json()
    assert body["total"] == 3 and "internal, not shown to users" in body["label"]
    by = {item["link_id"].rsplit("_", 1)[1]: item for item in body["items"]}
    general = by["general"]
    assert general["subject"] == {"type": "disease", "id": f"dis_{links}", "term": f"pretend ache {links}"}
    assert (general["system"], general["code"], general["title"], general["match_method"]) == (
        "ICD-11 MMS",
        f"ZZ{links}",
        "Pretend ache",
        "mondo_equivalent",
    )
    assert (general["review_status"], general["reviewer"], general["uri"]) == (
        "pending",
        None,
        f"http://example.invalid/ZZ{links}",
    )
    assert by["symptom"]["subject"]["type"] == "feature" and by["symptom"]["subject"]["term"] == f"pretend itch {links}"

    def total(**params):
        return client.get(PATH, params={"q": links, **params}, headers=reviewer.headers(None)).json()["total"]

    assert (total(system="HPO"), total(system="ICD-11 MMS"), total(subject_type="feature")) == (1, 2, 1)
    assert (total(subject_type="disease"), total(status="approved"), total(status="pending")) == (2, 0, 3)
    # The code and the vocabulary's title can be searched too, and paging is bounded.
    assert client.get(PATH, params={"q": f"zz{links}.0"}, headers=reviewer.headers(None)).json()["total"] == 1
    assert client.get(PATH, params={"q": "ache of the left"}, headers=reviewer.headers(None)).json()["total"] >= 1
    assert len(client.get(PATH, params={"q": links, "limit": 2}, headers=reviewer.headers(None)).json()["items"]) == 2
    assert "terminology_links" in client.get("/internal/v1/review/overview", headers=reviewer.headers(None)).json()


def test_a_decision_on_a_link_is_recorded_with_the_reviewer_and_changes_nothing_else(
    client, api: Api, reviewer: Api, links, owner_db
):
    def decide(key, status, note, who=reviewer):
        body = {"target_type": "terminology_link", "target_id": f"tl_{links}_{key}", "note": note, "status": status}
        return client.post(DECIDE, headers=who.headers(None), json=body)

    assert decide("general", "approved", "x", who=api).status_code == 403  # a user cannot decide a link
    approved = decide("general", "approved", "The general term is preferred.")
    assert approved.status_code == 200
    assert (approved.json()["previous_status"], approved.json()["review_status"]) == ("pending", "approved")
    assert decide("narrow", "rejected", "Only when the source says so.").status_code == 200
    signed = f"dev-reviewer:{reviewer.subject}"
    listed = client.get(PATH, params={"q": links}, headers=reviewer.headers(None)).json()["items"]
    assert {item["link_id"].rsplit("_", 1)[1]: (item["review_status"], item["reviewer"]) for item in listed} == {
        "general": ("approved", signed),
        "narrow": ("rejected", signed),
        "symptom": ("pending", None),
    }
    with owner_db.transaction(None) as tx:
        stored = tx.execute(select(TerminologyLink).where(TerminologyLink.link_id == f"tl_{links}_narrow")).scalar_one()
        # Only the status and the reviewer changed: the code, the title and the provenance are as written.
        assert (stored.status, stored.reviewer, stored.code, stored.title, stored.match_method, stored.detail) == (
            "rejected",
            signed,
            f"ZZ{links}.0",
            "Pretend ache of the left side",
            "exact_synonym",
            {"query": "pretend ache of the left side"},
        )
        notes = tx.execute(
            text("SELECT reviewer, note, status_change FROM review_notes WHERE target_id = :t"),
            {"t": f"tl_{links}_narrow"},
        ).all()
    assert [tuple(row) for row in notes] == [(signed, "Only when the source says so.", "rejected")]
    assert decide("missing", "rejected", "x").status_code == 404
    assert decide("general", "nonsense", "x").status_code == 422


@pytest.mark.postgres
def test_outside_a_reviewer_transaction_the_api_role_sees_and_changes_no_link(links, db):
    one = {"l": f"tl_{links}_general"}
    with db.transaction("dev:someone", role="user") as tx:  # what any user-facing request runs as
        assert tx.execute(text("SELECT count(*) FROM terminology_links WHERE link_id = :l"), one).scalar_one() == 0
        assert tx.execute(text("SELECT count(*) FROM terminology_links")).scalar_one() == 0
        assert (
            tx.execute(text("UPDATE terminology_links SET status = 'approved' WHERE link_id = :l"), one).rowcount == 0
        )
    with db.transaction("dev-reviewer:someone", role="reviewer") as tx:
        assert tx.execute(text("SELECT count(*) FROM terminology_links WHERE link_id = :l"), one).scalar_one() == 1
    # Even a reviewer transaction can change only the status and the reviewer; it cannot rewrite, add or remove a link.
    for statement in (
        "UPDATE terminology_links SET code = 'X' WHERE link_id = :l",
        "UPDATE terminology_links SET title = 'X' WHERE link_id = :l",
        "DELETE FROM terminology_links WHERE link_id = :l",
        "INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, match_method) "
        "SELECT :l || 'x', disease_id, system, system_version, code, title, match_method FROM terminology_links WHERE link_id = :l",
    ):
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            db.transaction("dev-reviewer:someone", role="reviewer") as tx,
        ):
            tx.execute(text(statement), one)
