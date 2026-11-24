"""The serving bundle, assembled from the current releases (M2.5f).

In clinical mode the service loads one file, the serving bundle. This module builds that file
from what has been approved and published, and from nothing else:

- the rules and questions of the current rule release;
- the features of the current mapping release, which must hold every feature a rule or a
  question names;
- the four response texts of the approved set;
- the current knowledge release, if there is one, by its ID. It must be pinned to the current
  mapping release. No candidates and no citations are taken from it yet: nothing defines them.

A part that is missing or not approved is named, and nothing is assembled. An assembled bundle
passes the clinical-mode checks. In clinical mode the service also refuses to start unless the
bundle it loaded is exactly what the current releases give, so a file that was edited, or
assembled before a release changed, is not served.

Assembling changes nothing in the database and switches nothing on.

Run `python -m feeltriva_api.serving_bundle` to write the file (by default to
`data/derived/serving_bundle.json`, outside Git).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from feeltriva_clinical import BundleError, ReleaseBundle, referenced_features, validate_bundle
from feeltriva_clinical.bundle import Feature, Question, Rule, Templates
from sqlalchemy import select

from . import publishing
from .auth import Principal
from .db import Database
from .models import PublishedKnowledge, PublishedMapping, ResponseTextSet, RuleRelease

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "derived" / "serving_bundle.json"


def _assemble(tx: Any) -> tuple[ReleaseBundle | None, dict[str, Any], list[str]]:
    """The bundle the current releases give, what it was built from, and everything that keeps it from existing."""
    problems: list[str] = []
    rule = tx.scalars(select(RuleRelease).where(RuleRelease.is_current)).first()
    mapping = publishing.current(tx, PublishedMapping)
    knowledge = publishing.current(tx, PublishedKnowledge)
    approved = tx.scalars(
        select(ResponseTextSet).where(ResponseTextSet.status == "approved").order_by(ResponseTextSet.set_id)
    ).all()
    texts = approved[0] if len(approved) == 1 else None
    if rule is None:
        problems.append("no rule release is current")
    if mapping is None:
        problems.append("no mapping release is current")
    if not approved:
        problems.append("the response texts are not approved")
    elif len(approved) > 1:
        problems.append("more than one set of response texts is approved: " + ", ".join(row.set_id for row in approved))
    if knowledge is not None and mapping is not None and knowledge.mapping_release != mapping.release_id:
        problems.append(
            f"the current knowledge release {knowledge.release_id} is pinned to the mapping release "
            f"{knowledge.mapping_release}, which is not the current one ({mapping.release_id})"
        )
    parts = {
        "rule_release": {"release_id": rule.release_id, "sha256": rule.sha256} if rule is not None else None,
        "mapping_release": {"release_id": mapping.release_id, "sha256": mapping.sha256}
        if mapping is not None
        else None,
        "response_texts": (
            {
                "set_id": texts.set_id,
                "version": texts.version,
                "fingerprint": texts.fingerprint,
                "by": texts.approved_by,
            }
            if texts is not None
            else None
        ),
        "knowledge_release": (
            {
                "release_id": knowledge.release_id,
                "sha256": knowledge.sha256,
                "mapping_release": knowledge.mapping_release,
            }
            if knowledge is not None
            else None
        ),
    }
    if rule is None or mapping is None or texts is None:
        return None, parts, problems
    features = [
        Feature(
            feature_id=entry["feature_id"],
            preferred_name=entry["preferred_name"],
            kind=entry["kind"],
            value_type=entry["value_type"],
            aliases=list(entry.get("aliases") or []),
            status="approved",
        )
        for entry in mapping.content["features"]
    ]
    rules = [Rule(**entry, status="approved") for entry in rule.content["rules"]]
    questions = [
        Question(
            question_id=entry["question_id"],
            feature_id=entry["feature_id"],
            wording=entry["wording"],
            answer_schema=entry["answer_schema"],
            applicability=entry.get("applicability") or None,
            evidence_ids=list(entry.get("evidence_ids") or []),
            status="approved",
        )
        for entry in rule.content["questions"]
    ]
    named = {feature for entry in rules for feature in referenced_features(entry.condition_ast)}
    named |= {question.feature_id for question in questions}
    missing = sorted(named - {feature.feature_id for feature in features})
    if missing:
        shown = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        problems.append(
            f"{len(missing)} features the rules or questions name are not in the current mapping release "
            f"{mapping.release_id}: {shown}"
        )
    if problems:
        return None, parts, problems
    bundle = ReleaseBundle(
        bundle_id=rule.bundle_id,
        rules_version=rule.release_id,
        knowledge_release_id=knowledge.working_id if knowledge is not None else None,
        knowledge_version=knowledge.release_id if knowledge is not None else None,
        synthetic=False,
        status="approved",
        features=features,
        rules=rules,
        questions=questions,
        candidates=[],
        evidence=[],
        templates=Templates(**texts.texts),
    )
    try:
        validate_bundle(bundle, clinical_mode=True)
    except BundleError as error:
        return None, parts, [f"the assembled bundle fails the clinical-mode check: {error}"]
    return bundle, parts, []


def _described(bundle: ReleaseBundle | None, parts: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    described: dict[str, Any] = {"assembled": bundle is not None, "problems": problems, "built_from": parts}
    if bundle is not None:
        described.update(
            {
                "bundle_id": bundle.bundle_id,
                "rules_version": bundle.rules_version,
                "knowledge_version": bundle.knowledge_version,
                "sha256": publishing.digest(bundle.model_dump()),
                "rules": len(bundle.rules),
                "features": len(bundle.features),
                "questions": len(bundle.questions),
                "candidates": len(bundle.candidates),
                "evidence": len(bundle.evidence),
                "response_texts": len(Templates.model_fields),
            }
        )
    return described


def assemble(db: Database) -> tuple[ReleaseBundle | None, dict[str, Any]]:
    """The serving bundle the current releases give (None when a part is missing), and its description."""
    with db.transaction(None) as tx:
        bundle, parts, problems = _assemble(tx)
        return bundle, _described(bundle, parts, problems)


def preview(db: Database, principal: Principal) -> dict[str, Any]:
    """What the serving bundle would hold now, or what keeps it from being assembled. For reviewers only."""
    principal.require_role("reviewer")
    return assemble(db)[1]


def verify_serving(db: Database, loaded: ReleaseBundle) -> None:
    """Refuse a loaded bundle that is not exactly what the current releases give."""
    bundle, described = assemble(db)
    if bundle is None:
        raise RuntimeError(
            "clinical mode requires a serving bundle the current releases give; missing: "
            + "; ".join(described["problems"])
        )
    if bundle != loaded:
        ours, theirs = bundle.model_dump(), loaded.model_dump()
        differing = sorted(key for key in ours if ours[key] != theirs[key])
        raise RuntimeError(
            "the loaded bundle is not what the current releases give; it differs in: " + ", ".join(differing)
        )


def write(db: Database, path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Write the serving bundle to a file, with a second file that says what it was built from."""
    bundle, described = assemble(db)
    if bundle is None:
        return described
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.model_dump(), indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8")
    manifest = path.with_suffix(".manifest.json")
    manifest.write_text(json.dumps(described, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8")
    return {**described, "path": str(path), "manifest": str(manifest)}


def main() -> int:
    from .settings import get_settings

    parser = argparse.ArgumentParser(description="Assemble the serving bundle from the current releases.")
    parser.add_argument("--out", type=Path, default=DEFAULT_PATH, help="where to write the bundle file")
    args = parser.parse_args()
    settings = get_settings()
    url = settings.migration_database_url or settings.database_url
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL or DATABASE_URL is required")
    result = write(Database(url), args.out)
    for name, part in result["built_from"].items():
        print(f"{name}: {part if part is not None else 'none'}")
    if not result["assembled"]:
        for problem in result["problems"]:
            print("MISSING", problem)
        print("nothing was written")
        return 1
    print(
        f"serving bundle {result['rules_version']}: {result['rules']} rules, {result['features']} features, "
        f"{result['questions']} questions, {result['response_texts']} response texts, "
        f"{result['candidates']} candidates; SHA-256 {result['sha256']}"
    )
    print(f"written to {result['path']}")
    print("it passes the clinical-mode checks; writing it serves nothing and switches nothing on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
