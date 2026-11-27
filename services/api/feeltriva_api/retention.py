"""Conversations are kept for 30 days and then deleted (owner decision E33; M3.16).

The consent text tells a person so, and this is what does it: every session started more than `days` ago is
deleted with everything that belongs to it (messages, observations, answers, assessments, replay records). The
audit record of a session stays without a link to it; it holds no health content.

It runs as the owner of the schema, because the application's own role can only ever see the sessions of the
caller it is serving. It has to be run every day; nothing in this repository schedules it yet (deployment,
M0.10 and M6.4). Until it is scheduled, the 30 days hold only as often as it is run.

    uv run python -m feeltriva_api.retention            # counts what would be deleted; changes nothing
    uv run python -m feeltriva_api.retention --delete   # deletes
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from .db import Database
from .models import (
    Assessment,
    AuditEvent,
    IdempotencyKey,
    Session,
    SessionAnswer,
    SessionMessage,
    SessionObservation,
)
from .settings import get_settings

DAYS = 30


def due(db: Database, *, now: datetime | None = None, days: int = DAYS) -> int:
    """How many sessions are older than the retention period. Reads only."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    with db.transaction(None, role="migration") as tx:
        return tx.scalar(select(func.count()).select_from(Session).where(Session.created_at < cutoff)) or 0


def purge(db: Database, *, now: datetime | None = None, days: int = DAYS) -> int:
    """Delete every session older than the retention period, with all that belongs to it."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    with db.transaction(None, role="migration") as tx:
        old = select(Session.session_id).where(Session.created_at < cutoff)
        # What belongs to a session is deleted here by name, not left to the database's own cascade: the
        # deletion must not depend on how a database is set up.
        for model in (SessionAnswer, Assessment, SessionObservation, SessionMessage, IdempotencyKey):
            tx.execute(delete(model).where(model.session_id.in_(old)))
        tx.execute(update(AuditEvent).where(AuditEvent.session_id.in_(old)).values(session_id=None))
        deleted = tx.execute(delete(Session).where(Session.created_at < cutoff))
        return int(deleted.rowcount)  # type: ignore[attr-defined]  # a DELETE gives a cursor result


def main() -> int:
    parser = argparse.ArgumentParser(prog="feeltriva_api.retention")
    parser.add_argument("--delete", action="store_true", help="delete (without it the sessions are only counted)")
    args = parser.parse_args()
    settings = get_settings()
    owner = Database(settings.migration_database_url or settings.database_url)
    if not args.delete:
        print(f"{due(owner)} conversations are older than {DAYS} days; nothing was changed (run with --delete)")
        return 0
    print(f"{purge(owner)} conversations older than {DAYS} days were deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
