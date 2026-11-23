"""Guarantees that only exist in PostgreSQL: forced row-level security for the application
role and transactional observation versions under real concurrency."""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

pytestmark = pytest.mark.postgres
CHILD_TABLES = ["session_messages", "session_observations", "assessments", "idempotency_keys", "audit_events"]


def test_application_role_is_not_privileged(db):
    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user")
        ).one()
        owns = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user")
        ).scalar_one()
    assert tuple(row) == (False, False, False, False) and owns == 0


def test_rls_hides_other_owners_rows_even_without_a_where_clause(db, api: Api, other: Api):
    mine = api.text(api.start({"age_years": 30}).json()["session_id"], 0, "alpha").json()
    theirs = other.text(other.start({"age_years": 30}).json()["session_id"], 0, "alpha").json()
    api.assess(mine["session_id"], 1)
    other.assess(theirs["session_id"], 1)

    with db.transaction(f"dev:{api.subject}") as tx:
        visible = {str(r[0]) for r in tx.execute(text("SELECT session_id FROM sessions"))}
        assert visible == {mine["session_id"]}  # unfiltered query, still only the caller's session
        for table in CHILD_TABLES:
            column = "session_id"
            ids = {str(r[0]) for r in tx.execute(text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"))}
            assert ids == {mine["session_id"]}, table
        # Cross-owner writes affect nothing.
        hijack = tx.execute(
            text("UPDATE sessions SET state = 'closed' WHERE session_id = :s"), {"s": theirs["session_id"]}
        )
        wipe = tx.execute(text("DELETE FROM session_observations WHERE session_id = :s"), {"s": theirs["session_id"]})
        assert hijack.rowcount == 0 and wipe.rowcount == 0

    with db.transaction(None) as tx:  # no caller bound to the transaction: nothing is visible
        assert tx.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0
    assert other.get(theirs["session_id"]).json()["state"] == "clarifying"


def test_rls_blocks_inserting_rows_for_another_owner_or_session(db, api: Api, other: Api):
    theirs = other.start({"age_years": 30}).json()["session_id"]
    with pytest.raises(DBAPIError, match="row-level security"), db.transaction(f"dev:{api.subject}") as tx:
        tx.execute(
            text(
                "INSERT INTO sessions(session_id, owner_subject, state, consent_version, expires_at) "
                "VALUES (:i, :o, 'intake', 'c', now() + interval '1 hour')"
            ),
            {"i": str(uuid.uuid4()), "o": f"dev:{other.subject}"},
        )
    with pytest.raises(DBAPIError, match="row-level security"), db.transaction(f"dev:{api.subject}") as tx:
        tx.execute(
            text(
                "INSERT INTO session_observations(observation_id, session_id, presence, observation_version) "
                "VALUES (:i, :s, 'present', 1)"
            ),
            {"i": str(uuid.uuid4()), "s": theirs},
        )


def test_application_role_cannot_alter_reference_or_schema(db):
    for statement in (
        "UPDATE features SET preferred_name = 'x'",
        "DELETE FROM features",
        "DELETE FROM rule_bundles",
        "INSERT INTO diseases(disease_id, preferred_name, status) VALUES ('x', 'x', 'approved')",
        "DROP TABLE sessions",
        "ALTER TABLE sessions DISABLE ROW LEVEL SECURITY",
        "DELETE FROM audit_events",
    ):
        with pytest.raises(DBAPIError, match="permission denied|must be owner"), db.transaction("dev:x") as tx:
            tx.execute(text(statement))
    # Since migration 0014 a reviewer decides a feature through the review path, so the role may set a feature's
    # status, but only in a reviewer's transaction: in a user's transaction the statement changes no row.
    with db.transaction("dev:x") as tx:
        before = tx.execute(text("SELECT count(*) FROM features WHERE status = 'approved'")).scalar_one()
        assert tx.execute(text("UPDATE features SET status = 'approved'")).rowcount == 0
        assert tx.execute(text("SELECT count(*) FROM features WHERE status = 'approved'")).scalar_one() == before


def test_concurrent_writers_on_one_version_exactly_one_wins(client, api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    barrier = threading.Barrier(6)
    codes: list[int] = []

    def write(i: int) -> None:
        barrier.wait()
        codes.append(api.text(sid, 0, f"alpha attempt {i}").status_code)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409, 409, 409, 409, 409]
    session = api.get(sid).json()
    assert session["observation_version"] == 1 and len(session["observations"]) == 1


def test_concurrent_identical_retries_apply_once(client, api: Api):
    sid = api.start({"age_years": 30}).json()["session_id"]
    key = uuid.uuid4().hex
    barrier = threading.Barrier(5)
    results: list[tuple[int, str]] = []

    def write() -> None:
        barrier.wait()
        r = api.text(sid, 0, "alpha", key=key)
        results.append((r.status_code, r.json().get("code", "")))

    threads = [threading.Thread(target=write) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Each concurrent duplicate either replays the stored response or is told to retry; none re-applies.
    assert all(status == 200 or code == "request_in_progress" for status, code in results), results
    assert any(status == 200 for status, _ in results)
    assert api.get(sid).json()["observation_version"] == 1
    assert api.text(sid, 0, "alpha", key=key).status_code == 200  # a later retry replays


def test_database_rejects_a_forked_correction_chain(owner_db, api: Api):
    session = api.text(api.start({"age_years": 30}).json()["session_id"], 0, "alpha").json()
    target = session["observations"][0]["observation_id"]
    insert = text(
        "INSERT INTO session_observations(observation_id, session_id, presence, observation_version, supersedes) "
        "VALUES (:i, :s, 'absent', 2, :t)"
    )
    with owner_db.transaction(None) as tx:
        tx.execute(insert, {"i": str(uuid.uuid4()), "s": session["session_id"], "t": target})
    with pytest.raises(DBAPIError, match="session_observations_supersedes_uidx"), owner_db.transaction(None) as tx:
        tx.execute(insert, {"i": str(uuid.uuid4()), "s": session["session_id"], "t": target})
