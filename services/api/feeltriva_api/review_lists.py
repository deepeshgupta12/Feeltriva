"""Small lists the review screens need beside the review targets themselves (M2.4h, M2.4i).

- `working_sets`: the sets a version can be published from: the sets of rules, the lists of names
  and the sets of texts and facts. A screen asks the service what the next version of one of them
  would hold, publishes it, or makes an earlier version the one in use.
- `list_questions`: the follow-up questions of the sets of rules, each decided like every other
  review target (`followup_question`).
- `list_rule_sets`: the sets of rules themselves, each approved as a whole (`rule_bundle`).

For reviewers only; nothing here is shown to a user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import Feature, FollowupQuestion, KnowledgeRelease, MappingRelease, RuleBundle
from .review import REVIEW_STATES, _page
from .review_rules import list_rules


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


def list_questions(
    db: Database, principal: Principal, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    """The follow-up questions with the set of rules each belongs to and the item it asks about."""
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    limit, offset = _page(limit, offset)
    wanted = [FollowupQuestion.status == status] if status else []
    with db.transaction(principal.subject, role="reviewer") as tx:
        total = tx.scalar(select(func.count()).select_from(FollowupQuestion).where(*wanted)) or 0
        rows = tx.execute(
            select(FollowupQuestion, Feature.preferred_name)
            .outerjoin(Feature, Feature.feature_id == FollowupQuestion.feature_id)
            .where(*wanted)
            .order_by(FollowupQuestion.bundle_id, FollowupQuestion.question_id)
            .limit(limit)
            .offset(offset)
        ).all()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "question_id": question.question_id,
                    "bundle_id": question.bundle_id,
                    "wording": question.wording,
                    "answer_type": (question.answer_schema or {}).get("type"),
                    "asks_about": {"id": question.feature_id, "term": name} if question.feature_id else None,
                    "review_status": question.status,
                }
                for question, name in rows
            ],
        }


def list_rule_sets(db: Database, principal: Principal) -> dict[str, Any]:
    """The sets of rules, each with its rules counted by decision and who approved the set."""
    sets = list_rules(db, principal, limit=1)["bundles"]
    return {"total": len(sets), "items": sets}
