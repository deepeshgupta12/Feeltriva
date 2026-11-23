"""Publishing a numbered release from a working set, and rollback (M2.5c2).

What the mapping release and the knowledge release have in common. A release is a snapshot of
what was approved in a working set at the time. It is numbered per working set, carries its
SHA-256 and the name of who published it, and is never edited or deleted: the database refuses
both. One release of a kind is current. A rollback makes an earlier release current again and
removes nothing. The same content is not published twice.

The functions here run inside the caller's reviewer transaction. What a release holds and what
keeps it from being published is decided by the caller. (Rule releases, M2.5b, were built before
this module and keep their own code in `releases.py`.)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select, update

from .auth import Principal
from .errors import ApiError
from .models import AuditEvent, ReviewNote


def digest(content: dict[str, Any]) -> str:
    plain = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def check_note(note: str) -> None:
    if not note.strip() or len(note) > 4000:
        raise ApiError(422, "invalid_note", "A note of 1 to 4000 characters is required.")


def latest(tx: Any, model: Any, working_id: str) -> Any:
    """The release of this working set with the highest number, or None."""
    return tx.scalars(
        select(model).where(model.working_id == working_id).order_by(model.number.desc()).limit(1)
    ).first()


def current(tx: Any, model: Any) -> Any:
    return tx.scalars(select(model).where(model.is_current)).first()


def summary(release: Any) -> dict[str, Any]:
    return {
        "release_id": release.release_id,
        "number": release.number,
        "sha256": release.sha256,
        "published_by": release.published_by,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "is_current": release.is_current,
    }


def outlook(tx: Any, model: Any, working_id: str, content: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    """What publishing this content now would do. Changes nothing."""
    sha = digest(content)
    last = latest(tx, model, working_id)
    same = last is not None and last.sha256 == sha
    return {
        "publishable": not problems and not same,
        "problems": problems,
        "same_as_release": last.release_id if same else None,
        "would_be_number": (last.number if last is not None else 0) + 1,
        "sha256": sha,
    }


def _record(tx: Any, principal: Principal, kind: str, release_id: str, note: str, event: str) -> None:
    tx.add(
        ReviewNote(
            note_id=uuid.uuid4(),
            target_type=kind,
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
            event_type=f"{kind}_{event}",
            redacted_metadata={"release_id": release_id},
        )
    )


def publish(
    tx: Any,
    model: Any,
    principal: Principal,
    *,
    kind: str,
    working_id: str,
    content: dict[str, Any],
    problems: list[str],
    note: str,
    **columns: Any,
) -> Any:
    """Store the content as the next release of its working set and make it the current one."""
    if problems:
        raise ApiError(409, "release_not_publishable", "This release cannot be published: " + "; ".join(problems) + ".")
    sha = digest(content)
    last = latest(tx, model, working_id)
    if last is not None and last.sha256 == sha:
        raise ApiError(409, "release_already_published", f"Nothing has changed since release {last.number}.")
    number = (last.number if last is not None else 0) + 1
    tx.execute(update(model).where(model.is_current).values(is_current=False))
    release = model(
        release_id=f"{working_id}.r{number}",
        working_id=working_id,
        number=number,
        content=content,
        sha256=sha,
        published_by=principal.subject,
        is_current=True,
        **columns,
    )
    tx.add(release)
    _record(tx, principal, kind, release.release_id, note, "published")
    tx.flush()
    tx.refresh(release)
    return release


def make_current(tx: Any, model: Any, principal: Principal, *, kind: str, release_id: str, note: str) -> Any:
    """Make a published release the current one: this is how a rollback is done. Nothing is removed."""
    release = tx.get(model, release_id)
    if release is None:
        raise ApiError(404, "release_not_found", "Release not found.")
    if release.is_current:
        raise ApiError(409, "release_already_current", "This release is already the current one.")
    tx.execute(update(model).where(model.is_current).values(is_current=False))
    tx.flush()
    release.is_current = True
    _record(tx, principal, kind, release_id, note, "made_current")
    tx.flush()
    return release
