"""Many rows decided at once (M2.4j).

A reviewer who has filtered a list records one decision, with one note, for every row shown. Each
row is decided exactly as a single decision is: its own rule is asked, its status is set, and it
gets its own note and its own audit record under the reviewer's name. Nothing about a single
decision is skipped because the rows come together.

Two ways:

- `decide_many`: all rows in one transaction. If the rule of one row refuses, nothing is changed
  and the answer names that row and gives the rule's own reason. This is what the screens use.
- `decide_each`: every row in its own transaction. A row its rule refuses is left as it was and is
  listed with the reason; the others are decided. This is for entering a decision that someone has
  given for a whole list, where the rows the rules refuse are to be reported, not to stop the rest.

A note without a decision is written on one row, not on many.
"""

from __future__ import annotations

from typing import Any

from .auth import Principal
from .db import Database
from .errors import ApiError
from .review import REVIEW_STATES, decide_in

MAX_ROWS = 200  # rows of one request; a longer list is decided page by page


def _rows(target_ids: list[str], status: str | None) -> list[str]:
    ids = list(dict.fromkeys(target_ids))
    if not ids or len(ids) > MAX_ROWS:
        raise ApiError(422, "invalid_row_count", f"Between 1 and {MAX_ROWS} rows are decided at once.")
    if status not in REVIEW_STATES:
        raise ApiError(
            422, "decision_required", "Deciding many rows at once needs a decision. A note alone is written on one row."
        )
    return ids


def decide_many(
    db: Database, principal: Principal, *, target_type: str, target_ids: list[str], note: str, status: str | None
) -> dict[str, Any]:
    """One decision for all the rows, or for none: a refusal names the row and changes nothing."""
    principal.require_role("reviewer")
    ids = _rows(target_ids, status)
    with db.transaction(principal.subject, role="reviewer") as tx:
        for target_id in ids:
            try:
                decide_in(tx, principal, target_type, target_id, note, status)
            except ApiError as refused:
                if refused.status == 422:
                    raise
                raise ApiError(
                    refused.status,
                    refused.code,
                    f"Nothing was changed. The row {target_id} cannot take this decision: {refused.message}",
                ) from refused
    return {
        "target_type": target_type,
        "review_status": status,
        "decided": len(ids),
        "refused": [],
        "reviewer": principal.subject,
    }


def decide_each(
    db: Database, principal: Principal, *, target_type: str, target_ids: list[str], note: str, status: str
) -> dict[str, Any]:
    """Each row in its own transaction; a refused row is left as it was and listed with the rule's reason."""
    principal.require_role("reviewer")
    decided, refused = 0, []
    for target_id in dict.fromkeys(target_ids):
        try:
            with db.transaction(principal.subject, role="reviewer") as tx:
                decide_in(tx, principal, target_type, target_id, note, status)
            decided += 1
        except ApiError as error:
            if error.status == 422:
                raise
            refused.append({"target_id": target_id, "code": error.code, "message": error.message})
    return {
        "target_type": target_type,
        "review_status": status,
        "decided": decided,
        "refused": refused,
        "reviewer": principal.subject,
    }
