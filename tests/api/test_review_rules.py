"""Rules and rule bundles in the review path (M2.5a): decided by a reviewer under their name; a bundle is
approved only when its rules are decided, its rule file is the one stored, and its numbers are confirmed.

An invented bundle with invented rules."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from feeltriva_api import review_rules
from feeltriva_api.models import ClinicalRule, RuleBundle
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

PATH = "/internal/v1/review/rules"
DECIDE = "/internal/v1/review/decisions"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def bundle(owner_db) -> str:
    """An invented bundle stored from a rule file, with one emergency and one urgent rule, all pending."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(
            RuleBundle(
                bundle_id=f"draft-{tag}",
                version=f"draft-{tag}-1",
                status="pending",
                manifest_uri=f"draft://draft-{tag}/draft-{tag}-1#sha256=fp-{tag}",
            )
        )
        tx.flush()
        for name, level, priority in (("hat", "emergency", 10), ("scarf", "urgent", 100)):
            tx.add(
                ClinicalRule(
                    rule_id=f"urg.{tag}.{name}",
                    bundle_id=f"draft-{tag}",
                    rule_type="urgency",
                    applicability={},
                    condition_ast={"op": "present", "feature": f"feat_{tag}_{name}"},
                    action={"type": "escalate", "urgency": level, "text": "Sample text (invented)."},
                    evidence_ids=["src.sample"],
                    priority=priority,
                    status="pending",
                )
            )
    return tag


def _file(tag: str, confirmed: str, fingerprint: str | None = None):
    """A stand-in for the rule file on disk: its fingerprint and one telephone number."""
    draft = SimpleNamespace(numbers=[SimpleNamespace(number="555", confirmed_by_owner=confirmed)])
    return lambda bundle_id: (draft, fingerprint or f"fp-{tag}") if bundle_id == f"draft-{tag}" else None


def test_rules_are_listed_for_reviewers_only_with_their_bundle(client, api: Api, reviewer: Api, bundle):
    assert client.get(PATH, headers=api.headers(None)).status_code == 403
    listed = client.get(PATH, params={"bundle_id": f"draft-{bundle}"}, headers=reviewer.headers(None))
    assert listed.status_code == 200
    body = listed.json()
    assert body["bundles"] == [
        {
            "bundle_id": f"draft-{bundle}",
            "version": f"draft-{bundle}-1",
            "review_status": "pending",
            "approved_by": None,
            "approved_at": None,
            "fingerprint": f"fp-{bundle}",
            "rules_by_status": {"pending": 2},
        }
    ]
    assert body["total"] == 2
    assert [
        (item["rule_id"], item["action"]["urgency"], item["review_status"], item["decided_by"])
        for item in body["items"]
    ] == [
        (f"urg.{bundle}.hat", "emergency", "pending", None),
        (f"urg.{bundle}.scarf", "urgent", "pending", None),
    ]
    only = client.get(
        PATH, params={"bundle_id": f"draft-{bundle}", "status": "approved"}, headers=reviewer.headers(None)
    )
    assert only.json()["total"] == 0
    assert client.get(PATH, params={"status": "nonsense"}, headers=reviewer.headers(None)).status_code == 422


def test_a_bundle_is_approved_only_when_its_rules_are_decided_and_its_file_and_numbers_are_checked(
    client, api: Api, reviewer: Api, bundle, owner_db, monkeypatch
):
    signed = f"dev-reviewer:{reviewer.subject}"

    def decide(target_type, target_id, status, note="Decided in a test.", who=reviewer):
        body = {"target_type": target_type, "target_id": target_id, "note": note, "status": status}
        return client.post(DECIDE, headers=who.headers(None), json=body)

    def approve_bundle():
        return decide("rule_bundle", f"draft-{bundle}", "approved")

    assert decide("clinical_rule", f"urg.{bundle}.hat", "approved", who=api).status_code == 403  # not a reviewer
    # While a rule is pending the bundle cannot be approved.
    refused = approve_bundle()
    assert (refused.status_code, refused.json()["code"]) == (409, "bundle_items_pending")
    # Each rule is decided on its own, under the reviewer's name, and nothing but its status changes.
    assert decide("clinical_rule", f"urg.{bundle}.hat", "approved", "Matches the published sign.").status_code == 200
    assert decide("clinical_rule", f"urg.{bundle}.scarf", "rejected", "Too broad.").status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        hat = tx.get(ClinicalRule, f"urg.{bundle}.hat")
        assert (hat.status, hat.priority, hat.action["text"]) == ("approved", 10, "Sample text (invented).")
        notes = tx.execute(
            text(
                "SELECT target_id, reviewer, note, status_change FROM review_notes WHERE target_id LIKE :t ORDER BY 1"
            ),
            {"t": f"urg.{bundle}.%"},
        ).all()
    assert [tuple(row) for row in notes] == [
        (f"urg.{bundle}.hat", signed, "Matches the published sign.", "approved"),
        (f"urg.{bundle}.scarf", signed, "Too broad.", "rejected"),
    ]
    listed = client.get(PATH, params={"bundle_id": f"draft-{bundle}"}, headers=reviewer.headers(None)).json()
    assert [(item["review_status"], item["decided_by"], item["decision_note"]) for item in listed["items"]] == [
        ("approved", signed, "Matches the published sign."),
        ("rejected", signed, "Too broad."),
    ]
    # The rule file is checked: it must be there, be the one that was stored, and have its numbers confirmed.
    monkeypatch.setattr(review_rules, "_rule_file", lambda bundle_id: None)
    assert approve_bundle().json()["code"] == "rule_file_missing"
    monkeypatch.setattr(review_rules, "_rule_file", _file(bundle, confirmed="2026-01-01", fingerprint="another"))
    assert approve_bundle().json()["code"] == "rule_file_changed"
    monkeypatch.setattr(review_rules, "_rule_file", _file(bundle, confirmed=""))
    unconfirmed = approve_bundle()
    assert unconfirmed.json()["code"] == "numbers_not_confirmed" and "555" in unconfirmed.json()["message"]
    with owner_db.transaction(None, role="migration") as tx:
        still = tx.get(RuleBundle, f"draft-{bundle}")
        assert (still.status, still.approved_by, still.approved_at) == ("pending", None, None)
    # With everything in place the approval is recorded on the bundle, with the reviewer and the time.
    monkeypatch.setattr(review_rules, "_rule_file", _file(bundle, confirmed="2026-01-01"))
    approved = approve_bundle()
    assert approved.status_code == 200 and approved.json()["review_status"] == "approved"
    after = client.get(PATH, params={"bundle_id": f"draft-{bundle}"}, headers=reviewer.headers(None)).json()["bundles"][
        0
    ]
    assert (after["review_status"], after["approved_by"], after["fingerprint"]) == ("approved", signed, f"fp-{bundle}")
    assert after["approved_at"] and after["rules_by_status"] == {"approved": 1, "rejected": 1}
    # An approved bundle's rules are not decided again until the approval is withdrawn, which names nobody.
    again = decide("clinical_rule", f"urg.{bundle}.scarf", "approved")
    assert (again.status_code, again.json()["code"]) == (409, "bundle_already_approved")
    assert decide("rule_bundle", f"draft-{bundle}", "pending", "Withdrawn to look again.").status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        withdrawn = tx.get(RuleBundle, f"draft-{bundle}")
        assert (withdrawn.status, withdrawn.approved_by, withdrawn.approved_at) == ("pending", None, None)
    assert decide("clinical_rule", f"urg.{bundle}.scarf", "approved").status_code == 200
    assert decide("clinical_rule", f"urg.{bundle}.missing", "approved").status_code == 404


def test_a_bundle_none_of_whose_rules_is_approved_cannot_be_approved(client, reviewer: Api, bundle, monkeypatch):
    monkeypatch.setattr(review_rules, "_rule_file", _file(bundle, confirmed="2026-01-01"))
    for name in ("hat", "scarf"):
        body = {
            "target_type": "clinical_rule",
            "target_id": f"urg.{bundle}.{name}",
            "note": "No.",
            "status": "rejected",
        }
        assert client.post(DECIDE, headers=reviewer.headers(None), json=body).status_code == 200
    body = {"target_type": "rule_bundle", "target_id": f"draft-{bundle}", "note": "Try.", "status": "approved"}
    refused = client.post(DECIDE, headers=reviewer.headers(None), json=body)
    assert (refused.status_code, refused.json()["code"]) == (409, "bundle_has_no_approved_rule")


@pytest.mark.postgres
def test_the_database_lets_only_a_reviewers_transaction_decide_and_only_the_status(db, bundle):
    rule = f"urg.{bundle}.hat"
    # A transaction that is not a reviewer's changes no row, whatever the code asks for.
    with db.transaction("someone") as tx:
        touched = tx.execute(text("UPDATE clinical_rules SET status = 'approved' WHERE rule_id = :r"), {"r": rule})
        assert touched.rowcount == 0
        assert (
            tx.execute(text("SELECT status FROM clinical_rules WHERE rule_id = :r"), {"r": rule}).scalar() == "pending"
        )
        moved = tx.execute(
            text("UPDATE rule_bundles SET status = 'approved' WHERE bundle_id = :b"), {"b": f"draft-{bundle}"}
        )
        assert moved.rowcount == 0
    # A reviewer's transaction may set the status, and nothing else.
    for statement in (
        "UPDATE clinical_rules SET priority = 1 WHERE rule_id = :r",
        "UPDATE clinical_rules SET action = '{}'::jsonb WHERE rule_id = :r",
        "DELETE FROM clinical_rules WHERE rule_id = :r",
    ):
        with pytest.raises(DBAPIError), db.transaction("rev", role="reviewer") as tx:
            tx.execute(text(statement), {"r": rule})
    with pytest.raises(DBAPIError), db.transaction("rev", role="reviewer") as tx:
        tx.execute(text("UPDATE rule_bundles SET manifest_uri = 'x' WHERE bundle_id = :b"), {"b": f"draft-{bundle}"})
