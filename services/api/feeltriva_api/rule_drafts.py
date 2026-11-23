"""Stores the draft urgency rule set as pending rows for review (M2.10).

The draft is a file in the clinical package (`feeltriva_clinical.urgency_draft`). This command
checks every feature the draft names against the feature vocabulary in the database, then writes
one `rule_bundles` row and one `clinical_rules` row per rule, all `pending`. It approves nothing,
and it never changes a row that a reviewer has decided. Serving does not read these tables.

Run with the schema-owner connection: `python -m feeltriva_api.rule_drafts`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from feeltriva_clinical.urgency_draft import DRAFT_PATH, UrgencyDraft, draft_digest, load_draft
from sqlalchemy import func, select

from .db import Database
from .models import ClinicalRule, Feature, RuleBundle


def store_draft(db: Database, draft: UrgencyDraft, digest: str) -> dict[str, Any]:
    """Store the draft as pending rows, or nothing when it names a feature the vocabulary does not hold."""
    result: dict[str, Any] = {
        "version": draft.version,
        "rules": len(draft.rules),
        "features": len(draft.features),
        "missing_features": [],
        "renamed_features": [],
        "bundle_decided": False,
        "decided_file_is_this_file": None,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "kept_decided": 0,
    }
    with db.transaction(None, role="migration") as tx:
        wanted = {feature.feature_id: feature.name for feature in draft.features}
        known = dict(
            tx.execute(select(Feature.feature_id, Feature.preferred_name).where(Feature.feature_id.in_(wanted))).all()
        )
        result["missing_features"] = sorted(set(wanted) - set(known))
        result["renamed_features"] = sorted(fid for fid, name in wanted.items() if fid in known and known[fid] != name)
        if result["missing_features"] or result["renamed_features"]:
            return result
        manifest = f"draft://{draft.draft_id}/{draft.version}#sha256={digest}"
        bundle = tx.get(RuleBundle, draft.draft_id)
        if bundle is None:
            tx.add(RuleBundle(bundle_id=draft.draft_id, version=draft.version, status="pending", manifest_uri=manifest))
            tx.flush()
        elif bundle.status != "pending" or bundle.approved_by:
            # A reviewer has decided on this bundle: nothing of it is rewritten. The command only compares.
            result["bundle_decided"] = True
            result["decided_file_is_this_file"] = bundle.manifest_uri == manifest
        else:
            bundle.version, bundle.manifest_uri = draft.version, manifest
        for rule in [] if result["bundle_decided"] else draft.rules:
            values = {
                "bundle_id": draft.draft_id,
                "rule_type": rule.rule_type,
                "applicability": {},
                "condition_ast": rule.condition_ast,
                "action": rule.action.model_dump(),
                "evidence_ids": list(rule.evidence_ids),
                "priority": rule.priority,
            }
            row = tx.get(ClinicalRule, rule.rule_id)
            if row is None:
                tx.add(ClinicalRule(rule_id=rule.rule_id, status="pending", **values))
                result["inserted"] += 1
            elif row.status != "pending":
                result["kept_decided"] += 1
            elif all(getattr(row, key) == value for key, value in values.items()):
                result["unchanged"] += 1
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                result["updated"] += 1
        tx.flush()
        of_bundle = ClinicalRule.bundle_id == draft.draft_id
        result["stored"] = {
            "bundle_status": tx.get(RuleBundle, draft.draft_id).status,  # type: ignore[union-attr]
            "rules": tx.scalar(select(func.count()).select_from(ClinicalRule).where(of_bundle)),
            "pending": tx.scalar(
                select(func.count()).select_from(ClinicalRule).where(of_bundle, ClinicalRule.status == "pending")
            ),
            "approved": tx.scalar(
                select(func.count()).select_from(ClinicalRule).where(of_bundle, ClinicalRule.status == "approved")
            ),
            "not_in_the_draft": tx.scalar(
                select(func.count())
                .select_from(ClinicalRule)
                .where(of_bundle, ClinicalRule.rule_id.not_in([rule.rule_id for rule in draft.rules]))
            ),
        }
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Everything that keeps the stored draft from being the draft file; empty when there is nothing."""
    diffs: list[str] = []
    if result["missing_features"]:
        diffs.append(
            f"{len(result['missing_features'])} features of the draft are not in the vocabulary; nothing stored"
        )
    if result["renamed_features"]:
        diffs.append(
            f"{len(result['renamed_features'])} features of the draft have another name in the vocabulary; nothing stored"
        )
    if result["bundle_decided"] and not result["decided_file_is_this_file"]:
        diffs.append(
            "a reviewer has decided on this bundle and the rule file has changed since; it is not rewritten: a "
            "changed rule set needs a new version"
        )
    stored = result.get("stored")
    if stored:
        if stored["rules"] - stored["not_in_the_draft"] != result["rules"]:
            diffs.append(f"{result['rules']} rules in the draft, {stored['rules']} stored")
        if stored["not_in_the_draft"]:
            diffs.append(f"{stored['not_in_the_draft']} stored rules of this bundle are not in the draft")
    return diffs


def report(result: dict[str, Any]) -> list[str]:
    lines = [f"urgency draft {result['version']}: {result['rules']} rules over {result['features']} features"]
    if "stored" in result:
        lines.append(
            f"inserted {result['inserted']}, updated {result['updated']}, unchanged {result['unchanged']}, "
            f"left because a reviewer decided {result['kept_decided']}"
        )
        lines.append(f"stored: {result['stored']}")
    if result["bundle_decided"]:
        same = "is" if result["decided_file_is_this_file"] else "is not"
        lines.append(
            f"a reviewer has decided on this bundle: nothing of it is rewritten; the rule file {same} the one decided on"
        )
    return lines


def main(path: Path = DRAFT_PATH) -> int:
    from .settings import get_settings

    settings = get_settings()
    url = settings.migration_database_url or settings.database_url
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL or DATABASE_URL is required")
    result = store_draft(Database(url), load_draft(path), draft_digest(path))
    print("\n".join(report(result)))
    diffs = check(result)
    for diff in diffs:
        print("DIFF", diff)
    stored = result.get("stored") or {}
    if diffs:
        print(f"{len(diffs)} differences")
    elif stored.get("pending") == result["rules"] and not result["bundle_decided"]:
        print(
            "every rule names features of the vocabulary and is stored pending; nothing is approved and nothing is served"
        )
    else:
        print(
            f"the stored rule set is the rule file: {stored.get('approved', 0)} of {result['rules']} rules approved, "
            f"bundle {stored.get('bundle_status')}; serving does not read these tables, so nothing is served"
        )
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
