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
    # It holds no rule, feature or source: the list then has no words for the invented rules (M2.4c).
    draft = SimpleNamespace(
        numbers=[SimpleNamespace(number="555", confirmed_by_owner=confirmed)], rules=[], features=[], sources=[]
    )
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
            "in_words_unavailable": "The rule file this rule set was stored from is not on this installation.",
        }
    ]
    assert [item["in_words"] for item in body["items"]] == [None, None]
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


# ---- the rules in words (M2.4c) ------------------------------------------------------------------------------


@pytest.fixture
def stored_from_the_rule_file(owner_db, monkeypatch):
    """The real rule file, stored under an invented bundle ID with its real fingerprint, and one of its rules altered."""
    from feeltriva_clinical.urgency_draft import draft_digest, load_draft

    tag = uuid.uuid4().hex[:10]
    draft, digest = load_draft(), draft_digest()
    bundle_id = f"words-{tag}"
    rules = sorted(draft.rules, key=lambda rule: rule.priority)[:3]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(
            RuleBundle(
                bundle_id=bundle_id,
                version=f"{bundle_id}-1",
                status="pending",
                manifest_uri=f"draft://{bundle_id}/{bundle_id}-1#sha256={digest}",
            )
        )
        tx.flush()
        for number, rule in enumerate(rules):
            action = rule.action.model_dump()
            if number == 2:  # a stored rule whose text is not the file's: its words must not be shown
                action["text"] = "A text that is not the one in the rule file (invented)."
            tx.add(
                ClinicalRule(
                    rule_id=f"{tag}.{rule.rule_id}",
                    bundle_id=bundle_id,
                    rule_type="urgency",
                    applicability={},
                    condition_ast=rule.condition_ast,
                    action=action,
                    evidence_ids=rule.evidence_ids,
                    priority=rule.priority,
                    status="pending",
                )
            )
    # The rule file belongs to this invented bundle, with the rule identifiers the bundle was stored under.
    renamed = draft.model_copy(
        update={
            "draft_id": bundle_id,
            "rules": [rule.model_copy(update={"rule_id": f"{tag}.{rule.rule_id}"}) for rule in draft.rules],
        }
    )
    state = {"digest": digest}
    monkeypatch.setattr(
        review_rules, "_rule_file", lambda wanted: (renamed, state["digest"]) if wanted == bundle_id else None
    )
    return SimpleNamespace(tag=tag, bundle_id=bundle_id, draft=draft, rules=rules, state=state)


def test_a_rule_is_shown_in_the_same_words_as_the_review_document(client, reviewer: Api, stored_from_the_rule_file):
    from pathlib import Path

    from feeltriva_clinical.urgency_documents import REVIEW_FILE

    stored = stored_from_the_rule_file
    document = (Path(__file__).resolve().parents[2] / "docs" / "review" / REVIEW_FILE).read_text(encoding="utf-8")
    body = client.get(PATH, params={"bundle_id": stored.bundle_id}, headers=reviewer.headers(None)).json()
    assert body["bundles"][0]["in_words_unavailable"] is None and body["total"] == 3
    first, second, altered = body["items"]
    rule = stored.rules[0]
    words = first["in_words"]
    assert (words["number"], words["of"], words["title"]) == (1, len(stored.draft.rules), rule.title)
    # The part of the document about this rule: from its heading to the next rule's heading.
    section = document.split(f"### Rule 1. {rule.title}", 1)[1].split("### Rule 2.", 1)[0]
    assert f"| **{words['level']}** | `{rule.rule_id}` | 1 of {words['of']} |" in section
    for line in words["fires_when"]:  # every line of the condition, at the depth the document lists it
        marked = f"**{line['text']}**" if line["heads_a_group"] else line["text"]
        assert f"{'  ' * line['depth']}- {marked}\n" in section
    assert len(words["fires_when"]) == section.split("**Fires when**")[1].split("**The person is shown**")[0].count(
        "- "
    )
    assert f"> {words['shown']}\n" in section and words["shown"] == first["action"]["text"]
    assert f"**Why this level.** {words['why_this_level']}\n" in section
    assert f"- Fires: {words['checked_with']['fires']}.\n" in section
    assert f"- Does not fire: {words['checked_with']['does_not_fire']}.\n" in section
    assert words["basis"] and len(words["basis"]) == len(rule.evidence_ids)
    for source in words["basis"]:
        reviewed = f", page last reviewed {source['page_reviewed']}" if source["page_reviewed"] else ""
        assert f"- {source['publisher']}, [{source['title']}]({source['url']}){reviewed}:\n" in section
        assert all(f"  - “{quote}”\n" in section for quote in source["quotes"])
    assert f"| {words['level']} | {words['level_meaning']} |" in document
    assert second["in_words"]["number"] == 2 and second["in_words"]["title"] == stored.rules[1].title
    # A stored rule whose text is not the file's is shown as stored, without words that would describe another text.
    assert altered["in_words"] is None and altered["action"]["text"].startswith("A text that is not")
    assert "differs from the rule in the rule file" in altered["in_words_unavailable"]
    assert first["in_words_unavailable"] is None

    # When the rule file has changed since the bundle was stored, no rule of it is put into words, and the reason is given.
    stored.state["digest"] = "another-fingerprint"
    changed = client.get(PATH, params={"bundle_id": stored.bundle_id}, headers=reviewer.headers(None)).json()
    assert "has changed since this rule set was stored" in changed["bundles"][0]["in_words_unavailable"]
    assert [item["in_words"] for item in changed["items"]] == [None, None, None]
    assert {item["in_words_unavailable"] for item in changed["items"]} == {changed["bundles"][0]["in_words_unavailable"]}
