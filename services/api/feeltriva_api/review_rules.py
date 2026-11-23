"""Rules, questions and rule bundles in the review path (M2.5a).

A reviewer decides each rule and question of a bundle, and then the bundle, through the same
decision endpoint as every other review target. The decision is recorded with the reviewer's
name; for a bundle the name and the time are also kept on the bundle itself.

Approving a bundle is refused unless

- every rule and question of it has been decided and at least one rule is approved;
- for a bundle stored from a rule file, the file on this installation is the one that was stored
  (same SHA-256 fingerprint), so the approval is for the text the reviewer read (decision E76);
- every telephone number the rule file names has been confirmed by the owner on its official page.

Once a bundle is approved, its rules and questions are not decided again until the approval is
withdrawn. Approving a bundle publishes nothing and serves nothing: publishing a release is a
later sub-step, and clinical mode loads only a published, approved release.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from feeltriva_clinical.urgency_draft import UrgencyDraft, draft_digest, load_draft
from sqlalchemy import func, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import ClinicalRule, FollowupQuestion, ReviewNote, RuleBundle
from .review import _GUARDS, _TARGETS, REVIEW_STATES, _page

_TARGETS["clinical_rule"] = (ClinicalRule, "rule_id")
_TARGETS["followup_question"] = (FollowupQuestion, "question_id")
_TARGETS["rule_bundle"] = (RuleBundle, "bundle_id")
_DRAFT = "draft://"


def _rule_file(bundle_id: str) -> tuple[UrgencyDraft, str] | None:
    """The rule file a bundle was stored from, with its fingerprint; None when this installation holds none."""
    draft = load_draft()
    return (draft, draft_digest()) if draft.draft_id == bundle_id else None


def _fingerprint(bundle: RuleBundle) -> str | None:
    marker = "#sha256="
    return bundle.manifest_uri.split(marker, 1)[1] if marker in bundle.manifest_uri else None


def _item_guard(tx: Any, item: Any, status: str, principal: Principal) -> None:
    bundle = tx.get(RuleBundle, item.bundle_id)
    if bundle is not None and bundle.status == "approved":
        raise ApiError(
            409,
            "bundle_already_approved",
            "This bundle is approved. Withdraw the bundle's approval before deciding one of its rules or questions.",
        )


def _bundle_guard(tx: Any, bundle: RuleBundle, status: str, principal: Principal) -> None:
    if status != "approved":
        bundle.approved_by, bundle.approved_at = None, None  # an approval that is withdrawn names nobody
        return
    counts: dict[str, int] = {}
    for model in (ClinicalRule, FollowupQuestion):
        rows = tx.execute(
            select(model.status, func.count()).where(model.bundle_id == bundle.bundle_id).group_by(model.status)
        ).all()
        for state, count in rows:
            counts[state] = counts.get(state, 0) + count
    approved_rules = tx.scalar(
        select(func.count())
        .select_from(ClinicalRule)
        .where(ClinicalRule.bundle_id == bundle.bundle_id, ClinicalRule.status == "approved")
    )
    if counts.get("pending"):
        raise ApiError(
            409, "bundle_items_pending", f"{counts['pending']} rules or questions of this bundle are still pending."
        )
    if not approved_rules:
        raise ApiError(409, "bundle_has_no_approved_rule", "No rule of this bundle is approved.")
    if bundle.manifest_uri.startswith(_DRAFT):
        held = _rule_file(bundle.bundle_id)
        if held is None:
            raise ApiError(409, "rule_file_missing", "The rule file this bundle was stored from is not available.")
        draft, digest = held
        if _fingerprint(bundle) != digest:
            raise ApiError(
                409,
                "rule_file_changed",
                "The rule file has changed since this bundle was stored. Store it again before approving.",
            )
        unconfirmed = [entry.number for entry in draft.numbers if not entry.confirmed_by_owner]
        if unconfirmed:
            raise ApiError(
                409,
                "numbers_not_confirmed",
                "The owner has not confirmed these telephone numbers on their official pages: "
                + ", ".join(unconfirmed)
                + ".",
            )
    bundle.approved_by, bundle.approved_at = principal.subject, datetime.now(UTC)


_GUARDS["clinical_rule"] = _item_guard
_GUARDS["followup_question"] = _item_guard
_GUARDS["rule_bundle"] = _bundle_guard


def list_rules(
    db: Database,
    principal: Principal,
    *,
    bundle_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """The rule bundles with their rules, each with its last recorded decision, for reviewers only."""
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    limit, offset = _page(limit, offset)
    with db.transaction(principal.subject, role="reviewer") as tx:
        wanted = [RuleBundle.bundle_id == bundle_id] if bundle_id else []
        bundles = tx.scalars(select(RuleBundle).where(*wanted).order_by(RuleBundle.bundle_id)).all()
        tally: dict[str, dict[str, int]] = {}
        for owner, state, count in tx.execute(
            select(ClinicalRule.bundle_id, ClinicalRule.status, func.count()).group_by(
                ClinicalRule.bundle_id, ClinicalRule.status
            )
        ).all():
            tally.setdefault(owner, {})[state] = count
        filters = [ClinicalRule.bundle_id == bundle_id] if bundle_id else []
        if status:
            filters.append(ClinicalRule.status == status)
        total = tx.scalar(select(func.count()).select_from(ClinicalRule).where(*filters)) or 0
        rules = tx.scalars(
            select(ClinicalRule)
            .where(*filters)
            .order_by(ClinicalRule.bundle_id, ClinicalRule.priority, ClinicalRule.rule_id)
            .limit(limit)
            .offset(offset)
        ).all()
        last: dict[str, ReviewNote] = {}
        if rules:
            notes = tx.scalars(
                select(ReviewNote)
                .where(
                    ReviewNote.target_type == "clinical_rule",
                    ReviewNote.target_id.in_([rule.rule_id for rule in rules]),
                    ReviewNote.status_change.is_not(None),
                )
                .order_by(ReviewNote.created_at)
            ).all()
            last = {note.target_id: note for note in notes}
        return {
            "bundles": [
                {
                    "bundle_id": bundle.bundle_id,
                    "version": bundle.version,
                    "review_status": bundle.status,
                    "approved_by": bundle.approved_by,
                    "approved_at": bundle.approved_at.isoformat() if bundle.approved_at else None,
                    "fingerprint": _fingerprint(bundle),
                    "rules_by_status": tally.get(bundle.bundle_id, {}),
                }
                for bundle in bundles
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "rule_id": rule.rule_id,
                    "bundle_id": rule.bundle_id,
                    "rule_type": rule.rule_type,
                    "priority": rule.priority,
                    "condition_ast": rule.condition_ast,
                    "action": rule.action,
                    "evidence_ids": rule.evidence_ids,
                    "review_status": rule.status,
                    "decided_by": last[rule.rule_id].reviewer if rule.rule_id in last else None,
                    "decision_note": last[rule.rule_id].note if rule.rule_id in last else None,
                }
                for rule in rules
            ],
        }
