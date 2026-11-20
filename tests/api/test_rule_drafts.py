"""Storing a draft rule set as pending rows (M2.10). An invented draft over invented features."""

from __future__ import annotations

import uuid

from feeltriva_api.models import ClinicalRule, Feature, RuleBundle
from feeltriva_api.rule_drafts import check, report, store_draft
from feeltriva_clinical.urgency_draft import UrgencyDraft, check_draft
from sqlalchemy import select


def _draft(tag: str, text: str = "Sample escalation text (invented, not medical guidance).") -> UrgencyDraft:
    hat, scarf = f"feat_{tag}_hat", f"feat_{tag}_scarf"
    draft = UrgencyDraft.model_validate(
        {
            "draft_id": f"draft-{tag}",
            "version": f"draft-{tag}-1",
            "status": "pending",
            "label": "Invented draft for a test.",
            "jurisdiction": "nowhere",
            "written": "2026-01-01",
            "sources": [
                {
                    "evidence_id": "src.sample",
                    "publisher": "Sample publisher",
                    "source_title": "Sample page",
                    "source_url": "https://example.org/sample",
                    "page_reviewed": "",
                    "licence": "none",
                    "quotes": ["A sample sentence."],
                }
            ],
            "features": [{"feature_id": hat, "name": f"hat {tag}"}, {"feature_id": scarf, "name": f"scarf {tag}"}],
            "rules": [
                {
                    "rule_id": f"urg.{tag}.{name}",
                    "rule_type": "urgency",
                    "title": f"Sample rule {name}",
                    "condition_ast": {"op": "present", "feature": feature},
                    "action": {"type": "escalate", "urgency": level, "text": text},
                    "evidence_ids": ["src.sample"],
                    "priority": priority,
                    "status": "pending",
                    "why_this_level": "Invented.",
                    "tests": [
                        {"present": [feature], "absent": [], "fires": True},
                        {"present": [], "absent": [feature], "fires": False},
                    ],
                }
                for name, feature, level, priority in (("hat", hat, "emergency", 10), ("scarf", scarf, "urgent", 100))
            ],
            "not_covered": [],
            "open_points": [],
        }
    )
    check_draft(draft)
    return draft


def _features(owner_db, tag: str, names=("hat", "scarf")) -> None:
    with owner_db.transaction(None, role="migration") as tx:
        for name in names:
            tx.add(
                Feature(
                    feature_id=f"feat_{tag}_{name}",
                    preferred_name=f"{name} {tag}",
                    kind="symptom",
                    value_type="boolean",
                )
            )


def _rows(owner_db, tag: str) -> dict[str, tuple[str, str]]:
    with owner_db.transaction(None, role="migration") as tx:
        rules = tx.scalars(select(ClinicalRule).where(ClinicalRule.bundle_id == f"draft-{tag}")).all()
        return {rule.rule_id: (rule.status, rule.action["text"]) for rule in rules}


def test_a_draft_is_stored_pending_once_and_a_reviewers_decision_is_not_rewritten(owner_db):
    tag = uuid.uuid4().hex[:10]
    _features(owner_db, tag)
    first = store_draft(owner_db, _draft(tag), "digest-1")
    assert check(first) == [] and (first["inserted"], first["updated"], first["unchanged"]) == (2, 0, 0)
    assert first["stored"] == {"bundle_status": "pending", "rules": 2, "pending": 2, "not_in_the_draft": 0}
    assert any("inserted 2" in line for line in report(first))
    with owner_db.transaction(None, role="migration") as tx:
        bundle = tx.get(RuleBundle, f"draft-{tag}")
        assert (bundle.status, bundle.approved_by, bundle.manifest_uri) == (
            "pending",
            None,
            f"draft://draft-{tag}/draft-{tag}-1#sha256=digest-1",
        )
        rule = tx.get(ClinicalRule, f"urg.{tag}.hat")
        assert (rule.status, rule.rule_type, rule.priority, rule.evidence_ids) == (
            "pending",
            "urgency",
            10,
            ["src.sample"],
        )
        assert rule.condition_ast == {"op": "present", "feature": f"feat_{tag}_hat"} and rule.applicability == {}
        assert rule.action == {"type": "escalate", "urgency": "emergency", "text": _draft(tag).rules[0].action.text}
    # A second run changes nothing.
    again = store_draft(owner_db, _draft(tag), "digest-1")
    assert check(again) == [] and (again["inserted"], again["updated"], again["unchanged"]) == (0, 0, 2)
    # A reviewer decides on one rule; a later change of the draft reaches only the rule still pending.
    with owner_db.transaction(None, role="migration") as tx:
        tx.get(ClinicalRule, f"urg.{tag}.hat").status = "rejected"
    changed = store_draft(owner_db, _draft(tag, "Another sample text (invented)."), "digest-2")
    assert check(changed) == [] and (changed["updated"], changed["kept_decided"]) == (1, 1)
    assert changed["stored"]["pending"] == 1
    assert _rows(owner_db, tag) == {
        f"urg.{tag}.hat": ("rejected", "Sample escalation text (invented, not medical guidance)."),
        f"urg.{tag}.scarf": ("pending", "Another sample text (invented)."),
    }
    # Once the bundle itself is decided, nothing of it is rewritten.
    with owner_db.transaction(None, role="migration") as tx:
        bundle = tx.get(RuleBundle, f"draft-{tag}")
        bundle.status, bundle.approved_by = "approved", "dev-reviewer:test"
    frozen = store_draft(owner_db, _draft(tag, "A third sample text (invented)."), "digest-3")
    assert frozen["bundle_decided"] and "stored" not in frozen
    assert any("a reviewer has decided on this bundle" in diff for diff in check(frozen))
    assert _rows(owner_db, tag)[f"urg.{tag}.scarf"] == ("pending", "Another sample text (invented).")


def test_a_draft_that_names_a_feature_the_vocabulary_does_not_hold_is_not_stored(owner_db):
    tag = uuid.uuid4().hex[:10]
    _features(owner_db, tag, names=("hat",))  # the scarf feature is missing
    missing = store_draft(owner_db, _draft(tag), "digest")
    assert missing["missing_features"] == [f"feat_{tag}_scarf"] and "stored" not in missing
    assert any("not in the vocabulary; nothing stored" in diff for diff in check(missing))
    assert _rows(owner_db, tag) == {}
    # A feature that exists under another name is not taken for the one the draft means.
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(
            Feature(feature_id=f"feat_{tag}_scarf", preferred_name=f"shawl {tag}", kind="symptom", value_type="boolean")
        )
    renamed = store_draft(owner_db, _draft(tag), "digest")
    assert renamed["renamed_features"] == [f"feat_{tag}_scarf"] and "stored" not in renamed
    assert any("another name in the vocabulary" in diff for diff in check(renamed)) and _rows(owner_db, tag) == {}
