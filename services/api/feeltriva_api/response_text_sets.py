"""The response texts of a release in the review path (M2.5f).

Every release bundle carries four texts a person is shown outside the rules. They are drafted in a
file of the clinical package (M2.5f1). This module stores them, as they stand in that file, for a
reviewer's decision, and lets a reviewer decide the set through the same decision endpoint as
every other review target.

Approving a set is refused unless the texts file on this installation is the one that was stored
(same SHA-256), so the approval is for the words the reviewer read, and unless the file passes its
own checks: exactly the four texts, no diagnosis, no percentage, and no telephone number the owner
has not confirmed. The database lets nobody change the texts of a decided set.

Approving the texts serves nothing. The serving bundle takes them from the approved set.

Run with the schema-owner connection to store the file: `python -m feeltriva_api.response_text_sets`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from feeltriva_clinical.response_texts import TEXTS_PATH, ResponseTextError, ResponseTexts, load_response_texts
from sqlalchemy import select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import ResponseTextSet
from .review import _GUARDS, _TARGETS

_TARGETS["response_texts"] = (ResponseTextSet, "set_id")


def texts_file(path: Path = TEXTS_PATH) -> tuple[ResponseTexts, str]:
    """The texts file, checked, with its SHA-256."""
    return load_response_texts(path), hashlib.sha256(path.read_bytes()).hexdigest()


def _guard(tx: Any, row: ResponseTextSet, status: str, principal: Principal) -> None:
    if status != "approved":
        row.approved_by, row.approved_at = None, None  # an approval that is withdrawn names nobody
        return
    try:
        draft, digest = texts_file()
    except (ResponseTextError, OSError, ValueError) as error:
        raise ApiError(409, "texts_file_not_in_order", f"The texts file does not pass its checks: {error}") from error
    if draft.draft_id != row.set_id or digest != row.fingerprint:
        raise ApiError(
            409,
            "texts_file_changed",
            "The texts file has changed since this set was stored. Store it again before approving.",
        )
    row.approved_by, row.approved_at = principal.subject, datetime.now(UTC)


_GUARDS["response_texts"] = _guard


def store_texts(db: Database, draft: ResponseTexts, digest: str) -> dict[str, Any]:
    """Store the texts of the file as a pending set. A decided set is never rewritten."""
    texts = draft.as_templates().model_dump()
    with db.transaction(None, role="migration") as tx:
        row = tx.get(ResponseTextSet, draft.draft_id)
        if row is None:
            row = ResponseTextSet(
                set_id=draft.draft_id, version=draft.version, fingerprint=digest, texts=texts, status="pending"
            )
            tx.add(row)
            outcome = "stored"
        elif row.fingerprint == digest:
            outcome = "unchanged"
        elif row.status != "pending":
            outcome = "kept: a reviewer has decided on this set and the file has changed since"
        else:
            row.version, row.fingerprint, row.texts = draft.version, digest, texts
            outcome = "replaced"
        tx.flush()
        return {
            "set_id": draft.draft_id,
            "version": draft.version,
            "fingerprint": digest,
            "outcome": outcome,
            "stored_status": row.status,
            "stored_is_this_file": row.fingerprint == digest,
            "approved_by": row.approved_by,
        }


def list_sets(db: Database, principal: Principal) -> dict[str, Any]:
    """The stored sets of response texts with their words and their decision, for reviewers only."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        rows = tx.scalars(select(ResponseTextSet).order_by(ResponseTextSet.set_id)).all()
        return {
            "label": "The four texts a person is shown outside the rules. Nothing is shown until a set is approved "
            "and a serving bundle built from it is served.",
            "items": [
                {
                    "set_id": row.set_id,
                    "version": row.version,
                    "fingerprint": row.fingerprint,
                    "texts": row.texts,
                    "review_status": row.status,
                    "approved_by": row.approved_by,
                    "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                }
                for row in rows
            ],
        }


def main(path: Path = TEXTS_PATH) -> int:
    from .settings import get_settings

    settings = get_settings()
    url = settings.migration_database_url or settings.database_url
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL or DATABASE_URL is required")
    draft, digest = texts_file(path)
    result = store_texts(Database(url), draft, digest)
    print(f"response texts {result['version']}: {len(draft.texts)} texts, SHA-256 {digest}")
    print(f"{result['outcome']}; the stored set is {result['stored_status']}")
    if not result["stored_is_this_file"]:
        print("DIFF the stored set is not this file: withdraw the decision on it before storing changed texts")
        return 1
    print("approving the set serves nothing: the serving bundle takes the texts from the approved set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
