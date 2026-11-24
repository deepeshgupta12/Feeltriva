"""Which stored rows carry a reviewer's decision (M2.5d1).

Everything the pipeline imports is `pending`. Only a reviewer may change that, through the review
path, and the review path records every decision in `review_notes` with the reviewer's name. The
self-checks of the pipeline were written when nothing had been reviewed and reported every row
that was not `pending` (BUG-021). A reviewed row is not a fault of the import. So a check reads a
row's standing, not its bare status:

- `pending`: as imported;
- `reviewed`: its present status is the last decision a reviewer recorded on it;
- any other value (its status as stored): changed with no reviewer's decision behind it. This is
  the only one of the three a self-check reports.

A disease label merged into another is `reviewed` too: the merge set it to `retired` and is
recorded in `disease_history` with the reviewer's name.

This module only builds SQL text from names fixed here. It reads no database.
"""

from __future__ import annotations

IN_ORDER = ("pending", "reviewed")

# table -> (review target type, key column, status column)
_TARGETS = {
    "sources": ("source", "source_id", "provenance_status"),
    "diseases": ("disease", "disease_id", "status"),
    "disease_mappings": ("disease_mapping", "mapping_id", "status"),
    "features": ("feature", "feature_id", "status"),
    "feature_mappings": ("feature_mapping", "mapping_id", "status"),
    "statements": ("statement", "statement_id", "status"),
    "disease_feature_evidence": ("evidence", "evidence_id", "status"),
}


def changed_by_no_reviewer(table: str, alias: str | None = None) -> str:
    """SQL condition: the row is not pending, and its status is not the last decision a reviewer recorded."""
    target, key, status = _TARGETS[table]
    row = alias or table
    last = (
        f"(SELECT n.status_change FROM review_notes n WHERE n.target_type = '{target}' "
        f"AND n.target_id = {row}.{key} AND n.status_change IS NOT NULL "
        "ORDER BY n.created_at DESC, n.note_id DESC LIMIT 1)"
    )
    condition = f"{row}.{status} <> 'pending' AND {last} IS DISTINCT FROM {row}.{status}::text"
    if table == "diseases":
        merged = (
            f"({row}.status = 'retired' AND {row}.redirected_to IS NOT NULL AND EXISTS (SELECT 1 FROM "
            f"disease_history h WHERE h.action = 'merge' AND h.disease_id = {row}.disease_id))"
        )
        condition += f" AND NOT {merged}"
    return f"({condition})"


def standing(table: str, alias: str | None = None) -> str:
    """SQL expression for a row's standing: 'pending', 'reviewed', or its status when nobody decided it."""
    row = alias or table
    status = _TARGETS[table][2]
    return (
        f"(CASE WHEN {row}.{status} = 'pending' THEN 'pending' "
        f"WHEN {changed_by_no_reviewer(table, alias)} THEN {row}.{status}::text ELSE 'reviewed' END)"
    )
