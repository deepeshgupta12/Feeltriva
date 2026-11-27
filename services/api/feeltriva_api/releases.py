"""Published rule releases, rollback, and what clinical mode may load (M2.5b).

A release is a snapshot of an approved bundle: its approved rules and questions, and the sources
the rules rest on. It is numbered, carries its SHA-256 and the name of who published it, and is
never edited or deleted. One release is current. A rollback makes an earlier release current
again; it removes nothing.

A bundle can be published only when it is approved, none of its rules or questions is pending,
at least one rule is approved, and its rule file is the one that was approved. Rules and questions
that were rejected are left out: an unapproved rule or question cannot be published.

In clinical mode the service refuses to start unless the rules of the bundle it loaded are exactly
the rules of the current release. Publishing does not switch clinical mode on, and a rule release
alone is not a serving bundle: features and response texts have their own approvals.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from feeltriva_clinical import ReleaseBundle, referenced_features
from sqlalchemy import func, select, update

from . import review_rules
from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import AuditEvent, ClinicalRule, FollowupQuestion, ReviewNote, RuleBundle, RuleRelease


def _digest(content: dict[str, Any]) -> str:
    plain = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _content(tx: Any, bundle: RuleBundle) -> tuple[dict[str, Any], list[str]]:
    """What a release of this bundle would hold, and everything that keeps it from being published."""
    problems: list[str] = []
    if bundle.status != "approved" or not bundle.approved_by:
        problems.append("the bundle is not approved")
    of_bundle = ClinicalRule.bundle_id == bundle.bundle_id
    rules = tx.scalars(
        select(ClinicalRule).where(of_bundle).order_by(ClinicalRule.priority, ClinicalRule.rule_id)
    ).all()
    questions = tx.scalars(
        select(FollowupQuestion)
        .where(FollowupQuestion.bundle_id == bundle.bundle_id)
        .order_by(FollowupQuestion.question_id)
    ).all()
    pending = sum(1 for item in [*rules, *questions] if item.status == "pending")
    if pending:
        problems.append(f"{pending} rules or questions are still pending")
    approved = [rule for rule in rules if rule.status == "approved"]
    if not approved:
        problems.append("no rule of the bundle is approved")
    fingerprint = review_rules._fingerprint(bundle)
    sources: dict[str, Any] = {}
    names: dict[str, str] = {}
    if bundle.manifest_uri.startswith("draft://"):
        held = review_rules._rule_file(bundle.bundle_id)
        if held is None:
            problems.append("the rule file this bundle was stored from is not available")
        else:
            draft, digest = held
            if digest != fingerprint:
                problems.append("the rule file has changed since the bundle was stored")
            sources = {source.evidence_id: source for source in draft.sources}
            names = {feature.feature_id: feature.question or feature.name for feature in draft.features}
    used = list(dict.fromkeys(evidence for rule in approved for evidence in rule.evidence_ids))
    missing = [evidence for evidence in used if evidence not in sources]
    if missing:
        problems.append(f"{len(missing)} sources named by approved rules are not in the rule file")
    features = sorted({feature for rule in approved for feature in referenced_features(rule.condition_ast)})
    content = {
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.version,
        "rule_file_fingerprint": fingerprint,
        "approved_by": bundle.approved_by,
        "approved_at": bundle.approved_at.isoformat() if bundle.approved_at else None,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "rule_type": rule.rule_type,
                "condition_ast": rule.condition_ast,
                "action": rule.action,
                "evidence_ids": rule.evidence_ids,
                "priority": rule.priority,
            }
            for rule in approved
        ],
        "questions": [
            {
                "question_id": question.question_id,
                "feature_id": question.feature_id,
                "wording": question.wording,
                "answer_schema": question.answer_schema,
                "applicability": question.applicability,
                "evidence_ids": question.evidence_ids,
                # Kept with the question since BUG-036; a question stored before that has none of them.
                "option_presence": dict((question.branch_rules or {}).get("option_presence") or {}),
                "priority": int((question.branch_rules or {}).get("priority", 100)),
                "essential": bool((question.branch_rules or {}).get("essential", False)),
                "stores": str((question.branch_rules or {}).get("stores", "observation")),
            }
            for question in questions
            if question.status == "approved"
        ],
        "evidence": [
            {
                "evidence_id": evidence,
                "publisher": sources[evidence].publisher,
                "source_title": sources[evidence].source_title,
                "source_url": sources[evidence].source_url,
                "page_reviewed": sources[evidence].page_reviewed,
                "licence": sources[evidence].licence,
                "quotes": list(sources[evidence].quotes),
            }
            for evidence in used
            if evidence in sources
        ],
        "features": [{"feature_id": feature, "name": names.get(feature, "")} for feature in features],
    }
    return content, problems


def _summary(release: RuleRelease) -> dict[str, Any]:
    content = release.content
    return {
        "release_id": release.release_id,
        "bundle_id": release.bundle_id,
        "number": release.number,
        "sha256": release.sha256,
        "rule_file_fingerprint": release.rule_file_fingerprint,
        "published_by": release.published_by,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "is_current": release.is_current,
        "rules": len(content["rules"]),
        "questions": len(content["questions"]),
        "evidence": len(content["evidence"]),
        "features": len(content["features"]),
    }


def _record(tx: Any, principal: Principal, release_id: str, note: str, event: str) -> None:
    tx.add(
        ReviewNote(
            note_id=uuid.uuid4(),
            target_type="rule_release",
            target_id=release_id,
            reviewer=principal.subject,
            note=note.strip(),
            status_change=event,
        )
    )
    tx.add(
        AuditEvent(
            event_id=uuid.uuid4(),
            actor_subject=principal.subject,
            event_type=event,
            redacted_metadata={"release_id": release_id},
        )
    )


def _note(note: str) -> None:
    if not note.strip() or len(note) > 4000:
        raise ApiError(422, "invalid_note", "A note of 1 to 4000 characters is required.")


def list_releases(db: Database, principal: Principal) -> dict[str, Any]:
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        releases = tx.scalars(select(RuleRelease).order_by(RuleRelease.bundle_id, RuleRelease.number)).all()
        return {"items": [_summary(release) for release in releases]}


def preview(db: Database, principal: Principal, bundle_id: str) -> dict[str, Any]:
    """What publishing this bundle now would do. Changes nothing."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        bundle = tx.get(RuleBundle, bundle_id)
        if bundle is None:
            raise ApiError(404, "bundle_not_found", "Rule bundle not found.")
        content, problems = _content(tx, bundle)
        sha = _digest(content)
        last = tx.scalars(
            select(RuleRelease).where(RuleRelease.bundle_id == bundle_id).order_by(RuleRelease.number.desc()).limit(1)
        ).first()
        return {
            "bundle_id": bundle_id,
            "publishable": not problems and not (last is not None and last.sha256 == sha),
            "problems": problems,
            "same_as_release": last.release_id if last is not None and last.sha256 == sha else None,
            "would_be_number": (last.number if last is not None else 0) + 1,
            "sha256": sha,
            "rules": len(content["rules"]),
            "questions": len(content["questions"]),
            "evidence": len(content["evidence"]),
            "features": len(content["features"]),
        }


def publish(db: Database, principal: Principal, *, bundle_id: str, note: str) -> dict[str, Any]:
    principal.require_role("reviewer")
    _note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        bundle = tx.get(RuleBundle, bundle_id)
        if bundle is None:
            raise ApiError(404, "bundle_not_found", "Rule bundle not found.")
        content, problems = _content(tx, bundle)
        if problems:
            raise ApiError(
                409, "release_not_publishable", "This bundle cannot be published: " + "; ".join(problems) + "."
            )
        sha = _digest(content)
        last = tx.scalars(
            select(RuleRelease).where(RuleRelease.bundle_id == bundle_id).order_by(RuleRelease.number.desc()).limit(1)
        ).first()
        if last is not None and last.sha256 == sha:
            raise ApiError(
                409, "release_already_published", f"Nothing has changed since release {last.number} of this bundle."
            )
        number = (last.number if last is not None else 0) + 1
        tx.execute(update(RuleRelease).where(RuleRelease.is_current).values(is_current=False))
        release = RuleRelease(
            release_id=f"{bundle_id}.r{number}",
            bundle_id=bundle_id,
            number=number,
            content=content,
            sha256=sha,
            rule_file_fingerprint=content["rule_file_fingerprint"],
            published_by=principal.subject,
            is_current=True,
        )
        tx.add(release)
        _record(tx, principal, release.release_id, note, "release_published")
        tx.flush()
        tx.refresh(release)
        return _summary(release)


def make_current(db: Database, principal: Principal, *, release_id: str, note: str) -> dict[str, Any]:
    """Make a published release the current one: this is how a rollback is done. Nothing is removed."""
    principal.require_role("reviewer")
    _note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        release = tx.get(RuleRelease, release_id)
        if release is None:
            raise ApiError(404, "release_not_found", "Release not found.")
        if release.is_current:
            raise ApiError(409, "release_already_current", "This release is already the current one.")
        tx.execute(update(RuleRelease).where(RuleRelease.is_current).values(is_current=False))
        tx.flush()
        release.is_current = True
        _record(tx, principal, release_id, note, "release_made_current")
        tx.flush()
        return _summary(release)


def verify_published(db: Database, bundle: ReleaseBundle) -> None:
    """Refuse a bundle whose rules are not exactly the rules of the current published release."""
    with db.transaction(None) as tx:
        current = tx.scalars(select(RuleRelease).where(RuleRelease.is_current)).first()
        total = tx.scalar(select(func.count()).select_from(RuleRelease)) or 0
        if current is None:
            raise RuntimeError(
                f"clinical mode requires a current published rule release; {total} releases exist and none is current"
            )
        published = {rule["rule_id"]: rule for rule in current.content["rules"]}
        loaded = {
            rule.rule_id: {
                "rule_id": rule.rule_id,
                "rule_type": rule.rule_type,
                "condition_ast": rule.condition_ast,
                "action": rule.action.model_dump(),
                "evidence_ids": list(rule.evidence_ids),
                "priority": rule.priority,
            }
            for rule in bundle.rules
        }
        if loaded != published:
            raise RuntimeError(
                f"the rules of the loaded bundle are not the rules of the current published release {current.release_id}"
            )
