"""Small lists the review screens need beside the review targets themselves (M2.4h, M2.4i).

- `working_sets`: the sets a version can be published from: the sets of rules, the lists of names
  and the sets of texts and facts. A screen asks the service what the next version of one of them
  would hold, publishes it, or makes an earlier version the one in use.

For reviewers only; nothing here is shown to a user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .auth import Principal
from .db import Database
from .models import KnowledgeRelease, MappingRelease, RuleBundle


def working_sets(db: Database, principal: Principal) -> dict[str, Any]:
    """The sets a version can be published from, by kind, each with its name in the system and its status."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        return {
            "rule_sets": [
                {"id": row.bundle_id, "version": row.version, "review_status": row.status}
                for row in tx.scalars(select(RuleBundle).order_by(RuleBundle.bundle_id)).all()
            ],
            "name_lists": [
                {"id": row.release_id, "version": row.version, "review_status": row.status}
                for row in tx.scalars(select(MappingRelease).order_by(MappingRelease.release_id)).all()
            ],
            "knowledge_sets": [
                {"id": row.release_id, "version": row.version, "review_status": row.status}
                for row in tx.scalars(select(KnowledgeRelease).order_by(KnowledgeRelease.release_id)).all()
            ],
        }
