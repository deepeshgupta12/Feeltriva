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


class _UndoneError(Exception):
    """Raised inside a transaction of a test to undo what it wrote."""


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
    # Even a reviewer transaction can change only the status and the reviewer of a stored link; it cannot rewrite or
    # remove one.
    for statement in (
        "UPDATE terminology_links SET code = 'X' WHERE link_id = :l",
        "UPDATE terminology_links SET title = 'X' WHERE link_id = :l",
        "DELETE FROM terminology_links WHERE link_id = :l",
    ):
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            db.transaction("dev-reviewer:someone", role="reviewer") as tx,
        ):
            tx.execute(text(statement), one)
    # Adding a link. Since M2.4b a reviewer transaction can: it is how the link is made when a reviewer confirms a
    # proposed term (tests/api/test_review_proposals.py). A user's transaction still cannot.
    add = text(
        """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, match_method)
           SELECT :l || :suffix, disease_id, system, system_version, code, title, match_method
           FROM terminology_links WHERE link_id = :l"""
    )
    with pytest.raises(_UndoneError), db.transaction("dev-reviewer:someone", role="reviewer") as tx:
        assert tx.execute(add, {**one, "suffix": "_added"}).rowcount == 1
        raise _UndoneError  # the row is not kept: other tests check the whole table
    with db.transaction("dev:someone", role="user") as tx:
        # A user's transaction reads no link, so there is nothing to copy; a row written out in full is refused.
        assert tx.execute(add, {**one, "suffix": "_by_user"}).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"), db.transaction("dev:someone", role="user") as tx:
        tx.execute(
            text(
                """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, match_method)
                   VALUES (:l || '_by_user', :d, 'ICD-11 MMS', 'test', 'X', 'made by a user', 'none')"""
            ),
            {**one, "d": f"dis_{links}"},
        )


# ---- what a decision on a link entails (M2.5d2) -------------------------------------------------------------


@pytest.fixture
def family(owner_db):
    """One invented disease with a MONDO link, two links taken through it, and three ICD-11 candidates of its own:
    one found by name, the unspecified sub-code of the category, and a narrower code under the category."""
    tag = uuid.uuid4().hex[:10]
    via = {"via": {"link_id": f"tl_{tag}_mondo", "vocabulary": "MONDO"}}
    rows = (
        ("mondo", "MONDO", f"MONDO:{tag}", "pretend ache", "exact_label", {}),
        ("snomed", "SNOMED CT", f"9{tag}", "pretend ache", "mondo_equivalent", via),
        ("category", "ICD-11 MMS", f"ZY{tag}", "Pretend ache", "mondo_equivalent", via),
        ("named", "ICD-11 MMS", f"ZX{tag}", "Pretend aching", "exact_title", {"also_through_mondo": via}),
        (
            "unspecified",
            "ICD-11 MMS",
            f"QQ{tag}",  # its code does not continue the category's: the recorded parent is what relates them
            "Pretend ache, unspecified",
            "exact_titleofotherentity",
            {"residual": True, "category_through_mondo": {"icd_code": f"ZY{tag}", "icd_title": "Pretend ache"}},
        ),
        ("narrow", "ICD-11 MMS", f"ZY{tag}.0", "Pretend ache of the left side", "exact_synonym", {}),
    )
    with owner_db.transaction(None) as tx:
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend ache {tag}"))
        tx.flush()
        for key, system, code, title, method, detail in rows:
            tx.add(
                TerminologyLink(
                    link_id=f"tl_{tag}_{key}",
                    disease_id=f"dis_{tag}",
                    system=system,
                    system_version="test",
                    code=code,
                    title=title,
                    uri=f"http://example.invalid/{code}",
                    match_method=method,
                    detail=detail,
                )
            )
    return tag


def _decide(client, who: Api, tag: str, key: str, status: str):
    body = {"target_type": "terminology_link", "target_id": f"tl_{tag}_{key}", "note": "Decided.", "status": status}
    return client.post(DECIDE, headers=who.headers(None), json=body)


def _statuses(owner_db, tag: str) -> dict[str, str]:
    with owner_db.transaction(None) as tx:
        rows = tx.execute(
            select(TerminologyLink.link_id, TerminologyLink.status).where(TerminologyLink.disease_id == f"dis_{tag}")
        ).all()
    return {link_id.rsplit("_", 1)[1]: status for link_id, status in rows}


def test_rejecting_a_mondo_link_retires_the_links_taken_through_it_and_withdrawing_brings_them_back(
    client, reviewer: Api, family, owner_db
):
    tag, signed = family, f"dev-reviewer:{reviewer.subject}"
    assert _decide(client, reviewer, tag, "mondo", "rejected").status_code == 200
    # The two links taken through it are retired. The link found by its own name is not: it rests on that name.
    assert _statuses(owner_db, tag) == {
        "mondo": "rejected",
        "snomed": "retired",
        "category": "retired",
        "named": "pending",
        "unspecified": "pending",
        "narrow": "pending",
    }
    with owner_db.transaction(None) as tx:
        link = tx.get(TerminologyLink, f"tl_{tag}_snomed")
        notes = tx.execute(
            text("SELECT reviewer, note, status_change FROM review_notes WHERE target_id = :t"),
            {"t": f"tl_{tag}_snomed"},
        ).all()
    assert link.reviewer == signed
    assert [tuple(row) for row in notes] == [
        (
            signed,
            f"Retired with the MONDO link it was taken through, which a reviewer rejected: tl_{tag}_mondo",
            "retired",
        )
    ]
    # A link is not approved while the MONDO link it rests on is rejected.
    refused = _decide(client, reviewer, tag, "category", "approved")
    assert (refused.status_code, refused.json()["code"]) == (409, "basis_rejected")
    # Withdrawing the rejection makes pending again what the rejection retired.
    assert _decide(client, reviewer, tag, "mondo", "pending").status_code == 200
    after = _statuses(owner_db, tag)
    assert (after["mondo"], after["snomed"], after["category"]) == ("pending", "pending", "pending")


def test_a_mondo_link_is_not_rejected_while_a_link_taken_through_it_is_approved(
    client, reviewer: Api, family, owner_db
):
    tag = family
    assert _decide(client, reviewer, tag, "category", "approved").status_code == 200
    refused = _decide(client, reviewer, tag, "mondo", "rejected")
    assert (refused.status_code, refused.json()["code"]) == (409, "derived_links_approved")
    assert f"tl_{tag}_category" in refused.json()["message"]
    # Refused whole: nothing was retired.
    before = _statuses(owner_db, tag)
    assert (before["mondo"], before["snomed"], before["category"]) == ("pending", "pending", "approved")
    # Once the reviewer has decided that link, the rejection goes through; a link already decided is left as it is.
    assert _decide(client, reviewer, tag, "category", "rejected").status_code == 200
    assert _decide(client, reviewer, tag, "mondo", "rejected").status_code == 200
    after = _statuses(owner_db, tag)
    assert (after["mondo"], after["snomed"], after["category"]) == ("rejected", "retired", "rejected")


def test_the_general_term_is_the_default_and_a_category_is_kept_before_its_unspecified_sub_code(
    client, reviewer: Api, family, owner_db
):
    tag = family
    # A narrower code, and the unspecified sub-code of the category, are not approved while the category stands.
    for key in ("narrow", "unspecified"):
        refused = _decide(client, reviewer, tag, key, "approved")
        assert (refused.status_code, refused.json()["code"]) == (409, "general_term_is_default"), key
        # The message names the general term and our own link ID, never a code of the vocabulary.
        message = refused.json()["message"]
        assert '"Pretend ache"' in message and f"tl_{tag}_category" in message and f"ZY{tag}" not in message
    assert _decide(client, reviewer, tag, "category", "approved").status_code == 200
    # Approving the category decides nothing else: the other candidates stay as they are, for their provenance.
    statuses = _statuses(owner_db, tag)
    assert (statuses["category"], statuses["narrow"], statuses["unspecified"]) == ("approved", "pending", "pending")
    assert _decide(client, reviewer, tag, "narrow", "approved").json()["code"] == "general_term_is_default"
    # A candidate that is not under another, and a link of another vocabulary, are approved as before.
    assert _decide(client, reviewer, tag, "named", "approved").status_code == 200
    assert _decide(client, reviewer, tag, "snomed", "approved").status_code == 200
    # When the source names the narrower form, the reviewer rejects the general term first.
    assert _decide(client, reviewer, tag, "category", "rejected").status_code == 200
    assert _decide(client, reviewer, tag, "narrow", "approved").status_code == 200
    assert _statuses(owner_db, tag)["narrow"] == "approved"


@pytest.mark.postgres
def test_a_link_a_reviewer_retired_is_not_brought_back_when_a_rejection_is_withdrawn(
    client, reviewer: Api, family, owner_db
):
    """On PostgreSQL only: the order of two decisions on one link is read from their recorded times."""
    tag = family
    assert _decide(client, reviewer, tag, "mondo", "rejected").status_code == 200
    assert _decide(client, reviewer, tag, "mondo", "pending").status_code == 200
    assert _decide(client, reviewer, tag, "snomed", "retired").status_code == 200  # the reviewer's own decision
    assert _decide(client, reviewer, tag, "mondo", "rejected").status_code == 200
    assert _decide(client, reviewer, tag, "mondo", "pending").status_code == 200
    after = _statuses(owner_db, tag)
    assert (after["snomed"], after["category"]) == ("retired", "pending")
