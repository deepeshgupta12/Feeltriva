"""Names without a link in the review path (M2.4b): reviewers only; confirming a proposed term makes its link,
rejecting makes none; a row without a term is not decided; the rules of every link apply; codes never in a refusal."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api.models import Disease, Feature, LinkProposal, ReviewNote, TerminologyLink
from feeltriva_api.review_proposals import KINDS, METHOD
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

PATH = "/internal/v1/review/link-proposals"
DECIDE = "/internal/v1/review/decisions"
ICD = "ICD-11 MMS"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


def _proposal(tag, key, subject, system, basis, code, title, **detail):
    disease = subject if subject.startswith("dis_") else None
    return LinkProposal(
        proposal_id=f"lp_{tag}_{key}",
        disease_id=disease,
        feature_id=None if disease else subject,
        system=system,
        system_version="test",
        basis=basis,
        reason=f"invented reason for {key}",
        code=code,
        title=title,
        uri=f"http://example.invalid/{code}" if code else None,
        link_id=f"tl_{tag}_{key}" if code else None,
        detail=detail,
    )


@pytest.fixture
def rows(owner_db):
    """Two invented diseases and one invented symptom, with rows of several kinds, and one general ICD-11 candidate."""
    tag = uuid.uuid4().hex[:10]
    ache, itch, glow = f"dis_{tag}_a", f"dis_{tag}_b", f"feat_{tag}"
    with owner_db.transaction(None) as tx:
        tx.add(Disease(disease_id=ache, preferred_name=f"pretend ache {tag}"))
        tx.add(Disease(disease_id=itch, preferred_name=f"pretend itch {tag}"))
        tx.add(Feature(feature_id=glow, preferred_name=f"pretend glow {tag}", kind="symptom", value_type="boolean"))
        tx.flush()
        tx.add_all(
            [
                _proposal(tag, "close", ache, ICD, "close_search_result", f"YA{tag}", "Pretend aching", score=0.93),
                _proposal(tag, "other", itch, ICD, "close_search_result", f"YB{tag}", "Pretend scratching", score=0.95),
                _proposal(tag, "near", glow, "HPO", "nearest_by_shared_words", f"HP:{tag}", "Pretend glowing"),
                _proposal(tag, "obsolete", glow, "MONDO", "term_not_linkable", f"MONDO:{tag}", "obsolete glow"),
                _proposal(tag, "none", glow, "MONDO", "no_term_near", None, None),
                # A close result that lies under a general candidate of the same disease.
                _proposal(tag, "narrow", itch, ICD, "close_search_result", f"YC{tag}.Z", "Pretend itch, unspecified"),
            ]
        )
        tx.add(
            TerminologyLink(
                link_id=f"tl_{tag}_general",
                disease_id=itch,
                system=ICD,
                system_version="test",
                code=f"YC{tag}",
                title="Pretend itch",
                uri="http://example.invalid/general",
                match_method="mondo_equivalent",
                detail={},
            )
        )
    return tag


def _name(who: Api) -> str:
    """The name the service records a decision under."""
    return f"dev-reviewer:{who.subject}"


def _decide(client, who: Api, tag: str, key: str, status: str | None, note: str = "decided in a test"):
    body = {"target_type": "link_proposal", "target_id": f"lp_{tag}_{key}", "note": note}
    if status:
        body["status"] = status
    return client.post(DECIDE, json=body, headers=who.headers(None))


def _link(owner_db, tag: str, key: str):
    with owner_db.transaction(None) as tx:
        link = tx.get(TerminologyLink, f"tl_{tag}_{key}")
        return None if link is None else (link.status, link.reviewer, link.match_method, link.code, link.title)


def _listed(client, who: Api, tag: str, **params):
    return client.get(PATH, params={"q": tag, **params}, headers=who.headers(None)).json()


def test_rows_are_listed_for_reviewers_only_those_that_can_be_confirmed_first(client, api: Api, reviewer: Api, rows):
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=api.headers(None)).status_code == 403  # a signed-in user is not a reviewer
    body = _listed(client, reviewer, rows)
    assert body["total"] == 6 and "nothing here is a link until a reviewer confirms it" in body["label"]
    keys = [item["proposal_id"].rsplit("_", 1)[1] for item in body["items"]]
    # By kind (close results, then nearest terms, then the rows that only record a reason), then by our name,
    # and for one name by the title of the term.
    assert keys == ["close", "narrow", "other", "near", "obsolete", "none"]
    by = dict(zip(keys, body["items"], strict=True))
    close = by["close"]
    assert close["subject"] == {"type": "disease", "id": f"dis_{rows}_a", "term": f"pretend ache {rows}"}
    assert close["term"] == {"code": f"YA{rows}", "title": "Pretend aching", "uri": f"http://example.invalid/YA{rows}"}
    assert (close["system"], close["basis"], close["meaning"], close["can_be_confirmed"]) == (
        ICD,
        "close_search_result",
        KINDS["close_search_result"],
        True,
    )
    assert (close["detail"], close["review_status"], close["reviewer"], close["link"]) == (
        {"score": 0.93},
        "pending",
        None,
        None,
    )
    assert (by["none"]["term"], by["none"]["can_be_confirmed"]) == (None, False)
    assert by["obsolete"]["term"]["title"] == "obsolete glow" and by["obsolete"]["can_be_confirmed"] is False
    assert by["near"]["subject"]["type"] == "feature" and by["near"]["reason"] == "invented reason for near"

    def total(**params):
        return _listed(client, reviewer, rows, **params)["total"]

    assert (total(system=ICD), total(system="HPO"), total(basis="close_search_result")) == (3, 1, 3)
    assert (total(decidable=True), total(decidable=False), total(subject_type="feature")) == (4, 2, 3)
    assert (total(status="pending"), total(status="approved"), total(basis="no_term_near")) == (6, 0, 1)
    # Our name, the term's title and the code can all be searched; a page is bounded.
    assert client.get(PATH, params={"q": f"ya{rows}"}, headers=reviewer.headers(None)).json()["total"] == 1
    assert len(_listed(client, reviewer, rows, limit=2)["items"]) == 2
    kinds = {kind["basis"]: kind for kind in body["kinds"]}
    assert list(kinds) == list(KINDS) and kinds["close_search_result"]["can_be_confirmed"] is True
    assert kinds["close_search_result"]["rows"] >= 3 and kinds["no_term_near"]["naming_a_term"] == 0


def test_confirming_one_close_result_makes_its_link_and_rejecting_another_makes_none(client, reviewer, rows, owner_db):
    assert _link(owner_db, rows, "close") is None  # a close result is not a link before a reviewer confirms it
    done = _decide(client, reviewer, rows, "close", "approved", "The search result names the same condition.")
    assert done.status_code == 200, done.text
    assert (done.json()["previous_status"], done.json()["review_status"], done.json()["reviewer"]) == (
        "pending",
        "approved",
        _name(reviewer),
    )
    assert _link(owner_db, rows, "close") == ("approved", _name(reviewer), METHOD, f"YA{rows}", "Pretend aching")
    refused = _decide(client, reviewer, rows, "other", "rejected", "Another condition.")
    assert refused.status_code == 200 and _link(owner_db, rows, "other") is None

    by = {item["proposal_id"].rsplit("_", 1)[1]: item for item in _listed(client, reviewer, rows)["items"]}
    assert (by["close"]["review_status"], by["close"]["reviewer"]) == ("approved", _name(reviewer))
    assert by["close"]["link"] == {"link_id": f"tl_{rows}_close", "review_status": "approved"}
    assert (by["other"]["review_status"], by["other"]["reviewer"], by["other"]["link"]) == (
        "rejected",
        _name(reviewer),
        None,
    )
    with owner_db.transaction(None) as tx:
        link = tx.get(TerminologyLink, f"tl_{rows}_close")
        # The link keeps where it came from: the row, its kind, its reason and what the look-up recorded.
        assert link.detail == {
            "score": 0.93,
            "proposal_id": f"lp_{rows}_close",
            "basis": "close_search_result",
            "reason": "invented reason for close",
        }
        assert (link.disease_id, link.system, link.system_version, link.uri) == (
            f"dis_{rows}_a",
            ICD,
            "test",
            f"http://example.invalid/YA{rows}",
        )
        notes = tx.scalars(
            select(ReviewNote).where(ReviewNote.target_id.in_([f"lp_{rows}_close", f"tl_{rows}_close"]))
        ).all()
        said = {(note.target_type, note.status_change, note.reviewer): note.note for note in notes}
    assert said[("link_proposal", "approved", _name(reviewer))] == "The search result names the same condition."
    assert said[("terminology_link", "approved", _name(reviewer))].startswith(
        f"Confirmed by a reviewer from the proposal lp_{rows}_close"
    )
    # The made link is an ordinary link: the links screen lists it with the reviewer.
    links = client.get(
        "/internal/v1/review/terminology-links", params={"q": f"YA{rows}"}, headers=reviewer.headers(None)
    ).json()
    assert [(item["match_method"], item["review_status"]) for item in links["items"]] == [(METHOD, "approved")]
    # Confirming again changes nothing and makes no second link or second record on it.
    assert _decide(client, reviewer, rows, "close", "approved").status_code == 200
    with owner_db.transaction(None) as tx:
        again = tx.scalars(select(ReviewNote).where(ReviewNote.target_id == f"tl_{rows}_close")).all()
    assert len(again) == 1


def test_the_link_a_row_made_follows_the_row_when_the_decision_changes(client, reviewer, rows, owner_db):
    assert _decide(client, reviewer, rows, "near", "approved").status_code == 200
    assert _link(owner_db, rows, "near")[:3] == ("approved", _name(reviewer), METHOD)
    assert _decide(client, reviewer, rows, "near", "rejected", "On a second look, not the same.").status_code == 200
    assert _link(owner_db, rows, "near")[0] == "rejected"
    assert _decide(client, reviewer, rows, "near", "pending", "Withdrawn for a second opinion.").status_code == 200
    assert _link(owner_db, rows, "near")[0] == "pending"
    with owner_db.transaction(None) as tx:
        trail = tx.scalars(
            select(ReviewNote).where(ReviewNote.target_id == f"tl_{rows}_near").order_by(ReviewNote.created_at)
        ).all()
    assert [note.status_change for note in trail] == ["approved", "rejected", "pending"]
    assert trail[1].note.startswith("Rejected with the proposal it was made from")


def test_a_row_without_a_term_is_not_decided_and_takes_a_note(client, reviewer, rows, owner_db):
    for key in ("none", "obsolete"):
        for status in ("approved", "rejected"):
            refused = _decide(client, reviewer, rows, key, status)
            assert refused.status_code == 409 and refused.json()["code"] == "nothing_to_confirm"
            assert "names no term that could be linked" in refused.json()["message"]
        assert _decide(client, reviewer, rows, key, None, "Checked by hand: no term fits.").status_code == 200
    retired = _decide(client, reviewer, rows, "close", "retired")
    assert retired.status_code == 409 and retired.json()["code"] == "proposal_not_retired"
    with owner_db.transaction(None) as tx:
        statuses = tx.execute(
            select(LinkProposal.status, LinkProposal.reviewer)
            .where(LinkProposal.proposal_id.like(f"lp_{rows}_%"))
            .distinct()
        ).all()
    assert [tuple(row) for row in statuses] == [("pending", None)]
    assert _link(owner_db, rows, "obsolete") is None


def test_the_rules_of_every_link_apply_to_a_confirmation_and_a_refusal_leaves_nothing_behind(
    client, reviewer, rows, owner_db
):
    refused = _decide(client, reviewer, rows, "narrow", "approved")
    assert refused.status_code == 409 and refused.json()["code"] == "general_term_is_default"
    # The message names the general term by its title and our own link ID, never a code.
    message = refused.json()["message"]
    assert '"Pretend itch"' in message and f"tl_{rows}_general" in message and f"YC{rows}" not in message
    assert _link(owner_db, rows, "narrow") is None  # no link was left behind by the refused confirmation
    assert _listed(client, reviewer, rows, basis="close_search_result", status="pending")["total"] == 3
    # Once the general term is rejected, the narrower one can be confirmed.
    general = {"target_type": "terminology_link", "target_id": f"tl_{rows}_general", "status": "rejected"}
    assert (
        client.post(
            DECIDE, json={**general, "note": "The source names the unspecified form."}, headers=reviewer.headers(None)
        ).status_code
        == 200
    )
    assert _decide(client, reviewer, rows, "narrow", "approved").status_code == 200
    assert _link(owner_db, rows, "narrow")[0] == "approved"


def test_a_link_that_came_by_another_route_is_approved_not_made_twice_and_does_not_follow_the_row(
    client, reviewer, rows, owner_db
):
    with owner_db.transaction(None) as tx:  # the same term reached by an import, as a pending candidate
        tx.add(
            TerminologyLink(
                link_id=f"tl_{rows}_close",
                disease_id=f"dis_{rows}_a",
                system=ICD,
                system_version="test",
                code=f"YA{rows}",
                title="Pretend aching",
                uri=f"http://example.invalid/YA{rows}",
                match_method="mondo_equivalent",
                detail={"marks": ["MONDO:equivalentTo"]},
            )
        )
    listed = _listed(client, reviewer, rows, basis="close_search_result")["items"]
    assert listed[0]["link"] == {"link_id": f"tl_{rows}_close", "review_status": "pending"}
    assert _decide(client, reviewer, rows, "close", "approved").status_code == 200
    assert _link(owner_db, rows, "close")[:3] == ("approved", _name(reviewer), "mondo_equivalent")
    # Rejecting the row afterwards leaves the link of the other route as it is.
    assert _decide(client, reviewer, rows, "close", "rejected").status_code == 200
    assert _link(owner_db, rows, "close")[0] == "approved"


@pytest.mark.postgres
def test_outside_a_reviewer_transaction_the_api_role_sees_no_row_and_makes_no_link(rows, db):
    with db.transaction("someone") as tx:  # an ordinary user's transaction
        assert tx.execute(text("SELECT count(*) FROM link_proposals")).scalar() == 0
        changed = tx.execute(
            text("UPDATE link_proposals SET status = 'approved' WHERE proposal_id = :p"), {"p": f"lp_{rows}_close"}
        )
        assert changed.rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"), db.transaction("someone") as tx:
        tx.execute(
            text(
                """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, match_method)
                   VALUES (:l, :d, 'ICD-11 MMS', 'test', 'X', 'made by a user', 'none')"""
            ),
            {"l": f"tl_{rows}_user", "d": f"dis_{rows}_a"},
        )
    with db.transaction("rev", role="reviewer") as tx:
        assert (
            tx.execute(
                text("SELECT count(*) FROM link_proposals WHERE proposal_id LIKE :p"), {"p": f"lp_{rows}_%"}
            ).scalar()
            == 6
        )
        # Even a reviewer's transaction changes only the decision of a row, never its term.
        with pytest.raises(DBAPIError, match="permission denied"):
            tx.execute(text("UPDATE link_proposals SET code = 'X' WHERE proposal_id = :p"), {"p": f"lp_{rows}_close"})
