"""Registers the loaded release's reference rows (features, bundle, questions, knowledge
release) so live-session foreign keys resolve. Idempotent. Rows keep the bundle's own review
status: seeding the synthetic fixture bundle approves nothing.

Run with the schema-owner connection: `python -m feeltriva_api.seed`.
"""

from __future__ import annotations

from feeltriva_clinical import ReleaseBundle

from .db import Database
from .models import Feature, FollowupQuestion, KnowledgeRelease, RuleBundle


def seed_release(db: Database, bundle: ReleaseBundle) -> None:
    with db.transaction(None, role="migration") as tx:
        if tx.get(RuleBundle, bundle.bundle_id) is None:
            tx.add(
                RuleBundle(
                    bundle_id=bundle.bundle_id,
                    version=bundle.rules_version,
                    status=bundle.status,
                    manifest_uri=f"bundle://{bundle.bundle_id}/{bundle.rules_version}",
                )
            )
        knowledge_id, knowledge_version = bundle.knowledge_release_id, bundle.knowledge_version
        # A bundle that carries no knowledge release names none, and none is registered for it.
        if (
            knowledge_id is not None
            and knowledge_version is not None
            and tx.get(KnowledgeRelease, knowledge_id) is None
        ):
            tx.add(
                KnowledgeRelease(
                    release_id=knowledge_id,
                    version=knowledge_version,
                    status=bundle.status,
                    manifest_uri=f"bundle://{knowledge_id}/{knowledge_version}",
                )
            )
        tx.flush()
        for f in bundle.features:
            row = tx.get(Feature, f.feature_id) or Feature(feature_id=f.feature_id)
            row.preferred_name, row.kind, row.value_type = f.preferred_name, f.kind, f.value_type
            row.aliases, row.status = list(f.aliases), f.status
            tx.add(row)
        tx.flush()
        for q in bundle.questions:
            row_q = tx.get(FollowupQuestion, q.question_id) or FollowupQuestion(question_id=q.question_id)
            row_q.bundle_id, row_q.feature_id, row_q.wording = bundle.bundle_id, q.feature_id, q.wording
            row_q.answer_schema, row_q.applicability = q.answer_schema, q.applicability or {}
            row_q.branch_rules, row_q.evidence_ids, row_q.status = {}, list(q.evidence_ids), q.status
            tx.add(row_q)


def main() -> None:
    from .container import load_release
    from .settings import get_settings

    settings = get_settings()
    url = settings.migration_database_url or settings.database_url
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL or DATABASE_URL is required")
    bundle = load_release(settings)
    seed_release(Database(url), bundle)
    print(f"seeded release {bundle.bundle_id} ({bundle.rules_version}); synthetic={bundle.synthetic}")


if __name__ == "__main__":
    main()
