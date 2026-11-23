"""Publishing a rule release, rollback, and what clinical mode may load (M2.5b). An invented bundle."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from feeltriva_api import review_rules
from feeltriva_api.models import ClinicalRule, RuleBundle, RuleRelease
from feeltriva_api.releases import verify_published
from feeltriva_clinical import load_fixture_bundle
from feeltriva_clinical.bundle import Feature, ReleaseBundle, Rule, RuleAction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

RELEASES = "/internal/v1/review/releases"
DECIDE = "/internal/v1/review/decisions"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def bundle(owner_db, monkeypatch) -> str:
    """An invented bundle stored from a rule file: three pending rules, and the file with its sources."""
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
        for name, level, priority, evidence in (
            ("hat", "emergency", 10, ["src.hat"]),
            ("scarf", "urgent", 100, ["src.scarf"]),
            ("coat", "urgent", 101, ["src.hat"]),
        ):
            tx.add(
                ClinicalRule(
                    rule_id=f"urg.{tag}.{name}",
                    bundle_id=f"draft-{tag}",
                    rule_type="urgency",
                    applicability={},
                    condition_ast={"op": "present", "feature": f"feat_{tag}_{name}"},
                    action={"type": "escalate", "urgency": level, "text": f"Sample text for {name} (invented)."},
                    evidence_ids=evidence,
                    priority=priority,
                    status="pending",
                )
            )
    sources = [
        SimpleNamespace(
            evidence_id=f"src.{name}",
            publisher="Sample publisher",
            source_title=f"Sample page {name}",
            source_url="https://example.org/sample",
            page_reviewed="",
            licence="none",
            quotes=[f"A sample sentence about a {name}."],
        )
        for name in ("hat", "scarf")
    ]
    features = [
        SimpleNamespace(feature_id=f"feat_{tag}_{name}", name=f"{name} {tag}", question=None)
        for name in ("hat", "scarf", "coat")
    ]
    draft = SimpleNamespace(
        sources=sources, features=features, numbers=[SimpleNamespace(number="555", confirmed_by_owner="2026-01-01")]
    )
    monkeypatch.setattr(
        review_rules, "_rule_file", lambda bundle_id: (draft, f"fp-{tag}") if bundle_id == f"draft-{tag}" else None
    )
    return tag


def _decide(client, who: Api, target_type: str, target_id: str, status: str):
    body = {"target_type": target_type, "target_id": target_id, "note": "Decided in a test.", "status": status}
    return client.post(DECIDE, headers=who.headers(None), json=body)


def test_only_an_approved_bundle_is_published_and_only_its_approved_rules(client, api: Api, reviewer: Api, bundle):
    bundle_id = f"draft-{bundle}"

    def preview():
        return client.get(f"{RELEASES}/preview", params={"bundle_id": bundle_id}, headers=reviewer.headers(None))

    def publish(who=reviewer):
        return client.post(
            RELEASES, headers=who.headers(None), json={"bundle_id": bundle_id, "note": "Publish in a test."}
        )

    assert client.get(RELEASES, headers=api.headers(None)).status_code == 403 and publish(api).status_code == 403
    # Nothing decided: the preview names every obstacle, and publishing is refused and writes nothing.
    first = preview().json()
    assert first["publishable"] is False and first["would_be_number"] == 1
    assert first["problems"] == [
        "the bundle is not approved",
        "3 rules or questions are still pending",
        "no rule of the bundle is approved",
    ]
    refused = publish()
    assert (refused.status_code, refused.json()["code"]) == (409, "release_not_publishable")
    assert client.get(RELEASES, headers=reviewer.headers(None)).json()["items"] == [] or all(
        item["bundle_id"] != bundle_id for item in client.get(RELEASES, headers=reviewer.headers(None)).json()["items"]
    )
    # Two rules approved, one rejected, the bundle approved: it can be published.
    assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.hat", "approved").status_code == 200
    assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.scarf", "approved").status_code == 200
    assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.coat", "rejected").status_code == 200
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "approved").status_code == 200
    ready = preview().json()
    assert (ready["publishable"], ready["problems"], ready["rules"], ready["evidence"], ready["features"]) == (
        True,
        [],
        2,
        2,
        2,
    )
    published = publish()
    assert published.status_code == 200
    release = published.json()
    signed = f"dev-reviewer:{reviewer.subject}"
    assert (release["release_id"], release["number"], release["is_current"], release["published_by"]) == (
        f"{bundle_id}.r1",
        1,
        True,
        signed,
    )
    assert (release["rules"], release["evidence"], release["sha256"], release["rule_file_fingerprint"]) == (
        2,
        2,
        ready["sha256"],
        f"fp-{bundle}",
    )
    # The same content cannot be published twice.
    again = publish()
    assert (again.status_code, again.json()["code"]) == (409, "release_already_published")
    assert preview().json()["same_as_release"] == f"{bundle_id}.r1"


def test_a_release_holds_what_was_approved_and_a_rollback_makes_an_earlier_one_current(
    client, reviewer: Api, bundle, owner_db
):
    bundle_id = f"draft-{bundle}"

    def publish():
        return client.post(RELEASES, headers=reviewer.headers(None), json={"bundle_id": bundle_id, "note": "Publish."})

    for name in ("hat", "scarf", "coat"):
        assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.{name}", "approved").status_code == 200
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "approved").status_code == 200
    assert publish().status_code == 200
    with owner_db.transaction(None, role="migration") as tx:
        first = tx.get(RuleRelease, f"{bundle_id}.r1")
        assert [rule["rule_id"] for rule in first.content["rules"]] == [
            f"urg.{bundle}.{n}" for n in ("hat", "scarf", "coat")
        ]
        assert first.content["rules"][0]["action"] == {
            "type": "escalate",
            "urgency": "emergency",
            "text": "Sample text for hat (invented).",
        }
        # The sources the approved rules rest on, with their quotes; the features the rules name.
        assert [(e["evidence_id"], e["quotes"]) for e in first.content["evidence"]] == [
            ("src.hat", ["A sample sentence about a hat."]),
            ("src.scarf", ["A sample sentence about a scarf."]),
        ]
        assert [feature["name"] for feature in first.content["features"]] == [
            f"coat {bundle}",
            f"hat {bundle}",
            f"scarf {bundle}",
        ]
        assert first.content["approved_by"] == f"dev-reviewer:{reviewer.subject}"
    # The approval is withdrawn, one rule is rejected, the bundle is approved again: a second release, now current.
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "pending").status_code == 200
    assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.coat", "rejected").status_code == 200
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "approved").status_code == 200
    second = publish()
    assert second.status_code == 200 and (
        second.json()["number"],
        second.json()["rules"],
        second.json()["is_current"],
    ) == (2, 2, True)

    def mine():
        return {
            item["release_id"]: item["is_current"]
            for item in client.get(RELEASES, headers=reviewer.headers(None)).json()["items"]
            if item["bundle_id"] == bundle_id
        }

    assert mine() == {f"{bundle_id}.r1": False, f"{bundle_id}.r2": True}
    # The first release still holds its three rules: publishing the second changed nothing in it.
    with owner_db.transaction(None, role="migration") as tx:
        assert len(tx.get(RuleRelease, f"{bundle_id}.r1").content["rules"]) == 3

    # Rollback: the first release is made current again. Nothing is removed.
    def switch(release_id):
        return client.post(
            f"{RELEASES}/current", headers=reviewer.headers(None), json={"release_id": release_id, "note": "Roll back."}
        )

    back = switch(f"{bundle_id}.r1")
    assert back.status_code == 200 and back.json()["is_current"] is True
    assert mine() == {f"{bundle_id}.r1": True, f"{bundle_id}.r2": False}
    assert (switch(f"{bundle_id}.r1").status_code, switch(f"{bundle_id}.r9").status_code) == (409, 404)
    with owner_db.transaction(None, role="migration") as tx:
        notes = tx.execute(
            text(
                "SELECT target_id, status_change, reviewer FROM review_notes WHERE target_id LIKE :t ORDER BY created_at"
            ),
            {"t": f"{bundle_id}.r%"},
        ).all()
    signed = f"dev-reviewer:{reviewer.subject}"
    assert [tuple(row) for row in notes] == [
        (f"{bundle_id}.r1", "release_published", signed),
        (f"{bundle_id}.r2", "release_published", signed),
        (f"{bundle_id}.r1", "release_made_current", signed),
    ]


def test_clinical_mode_accepts_only_the_rules_of_the_current_release(client, reviewer: Api, bundle, db):
    bundle_id = f"draft-{bundle}"
    for name in ("hat", "scarf", "coat"):
        assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.{name}", "approved").status_code == 200
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "approved").status_code == 200
    body = {"bundle_id": bundle_id, "note": "Publish."}
    assert client.post(RELEASES, headers=reviewer.headers(None), json=body).status_code == 200

    def serving(texts: dict[str, str], names=("hat", "scarf", "coat")) -> ReleaseBundle:
        levels = {
            "hat": ("emergency", 10, ["src.hat"]),
            "scarf": ("urgent", 100, ["src.scarf"]),
            "coat": ("urgent", 101, ["src.hat"]),
        }
        return ReleaseBundle(
            bundle_id="serving",
            rules_version="serving-1",
            knowledge_release_id="none",
            knowledge_version="none",
            synthetic=False,
            status="approved",
            features=[
                Feature(feature_id=f"feat_{bundle}_{name}", preferred_name=name, status="approved") for name in names
            ],
            rules=[
                Rule(
                    rule_id=f"urg.{bundle}.{name}",
                    rule_type="urgency",
                    condition_ast={"op": "present", "feature": f"feat_{bundle}_{name}"},
                    action=RuleAction(
                        type="escalate",
                        urgency=levels[name][0],
                        text=texts.get(name, f"Sample text for {name} (invented)."),
                    ),
                    evidence_ids=levels[name][2],
                    priority=levels[name][1],
                    status="approved",
                )
                for name in names
            ],
            questions=[],
            candidates=[],
            evidence=[],
            templates=load_fixture_bundle().templates,
        )

    verify_published(db, serving({}))  # exactly the published rules: accepted
    with pytest.raises(RuntimeError, match="not the rules of the current published release"):
        verify_published(db, serving({"hat": "Another text that nobody approved."}))
    with pytest.raises(RuntimeError, match="not the rules of the current published release"):
        verify_published(db, serving({}, names=("hat", "scarf")))  # a published rule is missing
    with pytest.raises(RuntimeError, match="not the rules of the current published release"):
        verify_published(db, load_fixture_bundle())  # the synthetic sample release is not a published release


@pytest.mark.postgres
def test_the_database_refuses_to_edit_or_delete_a_release_and_lets_only_a_reviewer_publish(
    client, reviewer: Api, bundle, db, owner_db
):
    bundle_id = f"draft-{bundle}"
    assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.hat", "approved").status_code == 200
    for name in ("scarf", "coat"):
        assert _decide(client, reviewer, "clinical_rule", f"urg.{bundle}.{name}", "rejected").status_code == 200
    assert _decide(client, reviewer, "rule_bundle", bundle_id, "approved").status_code == 200
    body = {"bundle_id": bundle_id, "note": "Publish."}
    assert client.post(RELEASES, headers=reviewer.headers(None), json=body).status_code == 200
    release = {"r": f"{bundle_id}.r1"}
    # Even the owner of the schema cannot edit or delete a published release.
    for statement, message in (
        ("UPDATE rule_releases SET content = '{}'::jsonb WHERE release_id = :r", "cannot be edited"),
        ("UPDATE rule_releases SET sha256 = 'x' WHERE release_id = :r", "cannot be edited"),
        ("UPDATE rule_releases SET published_by = 'someone else' WHERE release_id = :r", "cannot be edited"),
        ("DELETE FROM rule_releases WHERE release_id = :r", "cannot be deleted"),
    ):
        with pytest.raises(DBAPIError, match=message), owner_db.transaction(None, role="migration") as tx:
            tx.execute(text(statement), release)
    # Outside a reviewer's transaction the application role can neither publish nor change which release is current.
    with db.transaction("someone") as tx:
        assert (
            tx.execute(text("UPDATE rule_releases SET is_current = false WHERE release_id = :r"), release).rowcount == 0
        )
    with pytest.raises(DBAPIError), db.transaction("someone") as tx:
        tx.execute(
            text(
                "INSERT INTO rule_releases (release_id, bundle_id, number, content, sha256, published_by) "
                "VALUES (:i, :b, 99, '{}'::jsonb, 'x', 'someone')"
            ),
            {"i": f"{bundle_id}.r99", "b": bundle_id},
        )
