"""Shared fixtures.

Default backend is in-memory SQLite (fast, no services). Set TEST_DATABASE_URL (application
role) and TEST_MIGRATION_DATABASE_URL (schema owner) to run the same suite on PostgreSQL with
migrations and row-level security applied; tests marked `postgres` only run there.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from feeltriva_api.consent import current as current_consent
from feeltriva_api.container import Container, build_container
from feeltriva_api.db import Database
from feeltriva_api.main import create_app
from feeltriva_api.models import Base
from feeltriva_api.seed import seed_release
from feeltriva_api.settings import Settings
from feeltriva_clinical import load_fixture_bundle
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PG_APP = os.environ.get("TEST_DATABASE_URL", "")
PG_OWNER = os.environ.get("TEST_MIGRATION_DATABASE_URL", "")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_pg = pytest.mark.skip(reason="set TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL to run")
    skip_archives = pytest.mark.skip(reason="source archives not present in data/raw")
    have_archives = all((ROOT / "data" / "raw" / f"archive({i}).zip").exists() for i in range(11, 17))
    for item in items:
        if "postgres" in item.keywords and not (PG_APP and PG_OWNER):
            item.add_marker(skip_pg)
        if "archives" in item.keywords and not have_archives:
            item.add_marker(skip_archives)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_mode="mock",
        database_url=PG_APP or "sqlite://",
        clinical_mode_enabled=False,
        session_encryption_key="",
    )


@pytest.fixture(scope="session")
def owner_db() -> Database:
    """Schema-owner connection: migrations, seeding and direct inspection in tests."""
    if PG_APP and PG_OWNER:
        from alembic import command
        from alembic.config import Config

        os.environ["MIGRATION_DATABASE_URL"] = PG_OWNER
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        db = Database(PG_OWNER)
    else:
        db = Database("sqlite://")
        Base.metadata.create_all(db.engine)
    seed_release(db, load_fixture_bundle())
    return db


@pytest.fixture(scope="session")
def db(owner_db: Database) -> Database:
    """Connection the application uses (least-privilege role on PostgreSQL)."""
    return Database(PG_APP) if PG_APP and PG_OWNER else owner_db


@pytest.fixture(scope="session")
def container(settings: Settings, db: Database) -> Container:
    return build_container(settings, db)


@pytest.fixture(scope="session")
def client(settings: Settings, container: Container) -> TestClient:
    return TestClient(create_app(settings, container), raise_server_exceptions=False)


class Api:
    """A caller with its own subject. Generates a fresh Idempotency-Key per mutation unless given."""

    def __init__(self, client: TestClient, subject: str | None = None, token: str | None = None) -> None:
        self.client = client
        self.subject = subject or f"user-{uuid.uuid4().hex[:12]}"
        self.token = token or f"dev:{self.subject}"

    def headers(self, key: str | None = "auto") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if key is not None:
            headers["Idempotency-Key"] = uuid.uuid4().hex if key == "auto" else key
        return headers

    def start(self, demographics: dict[str, Any] | None = None, key: str = "auto") -> Any:
        body: dict[str, Any] = {"consent_version": CONSENT}
        if demographics is not None:
            body["demographics"] = demographics
        return self.client.post("/v1/sessions", json=body, headers=self.headers(key))

    def get(self, sid: str) -> Any:
        return self.client.get(f"/v1/sessions/{sid}", headers=self.headers(None))

    def text(self, sid: str, version: int, text: str, key: str = "auto") -> Any:
        return self.client.post(
            f"/v1/sessions/{sid}/observations",
            headers=self.headers(key),
            json={"observation_version": version, "text": text},
        )

    def observe(self, sid: str, version: int, observations: list[dict[str, Any]], key: str = "auto") -> Any:
        return self.client.post(
            f"/v1/sessions/{sid}/observations",
            headers=self.headers(key),
            json={"observation_version": version, "observations": observations},
        )

    def answer(self, sid: str, version: int, question_id: str, answer: Any, key: str = "auto") -> Any:
        return self.client.post(
            f"/v1/sessions/{sid}/answers",
            headers=self.headers(key),
            json={"observation_version": version, "question_id": question_id, "answer": answer},
        )

    def next_question(self, sid: str, version: int) -> Any:
        return self.client.get(
            f"/v1/sessions/{sid}/next-question", params={"observation_version": version}, headers=self.headers(None)
        )

    def assess(self, sid: str, version: int, key: str = "auto") -> Any:
        return self.client.post(
            f"/v1/sessions/{sid}/assessments", headers=self.headers(key), json={"observation_version": version}
        )

    def summary(self, sid: str, version: int, key: str = "auto") -> Any:
        return self.client.post(
            f"/v1/sessions/{sid}/summary", headers=self.headers(key), json={"observation_version": version}
        )

    def delete(self, sid: str, key: str = "auto") -> Any:
        return self.client.delete(f"/v1/sessions/{sid}", headers=self.headers(key))

    # -- composite helpers -------------------------------------------------
    def confirm_all(self, session: dict[str, Any]) -> dict[str, Any]:
        """Confirm every unconfirmed, concept-mapped observation exactly as interpreted."""
        pending = [o for o in session["observations"] if o["feature_id"] and not o["confirmed"]]
        if not pending:
            return session
        r = self.observe(
            session["session_id"],
            session["observation_version"],
            [
                {
                    "feature_id": o["feature_id"],
                    "presence": o["presence"],
                    "confirmed": True,
                    "supersedes": o["observation_id"],
                }
                for o in pending
            ],
        )
        assert r.status_code == 200, r.text
        return r.json()

    def answer_all(self, session: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
        """Answer follow-ups one at a time, as the server asks them, until there are none."""
        while True:
            r = self.next_question(session["session_id"], session["observation_version"])
            if r.status_code == 204:
                return session
            assert r.status_code == 200, r.text
            question = r.json()
            r = self.answer(
                session["session_id"],
                session["observation_version"],
                question["question_id"],
                answers[question["question_id"]],
            )
            assert r.status_code == 200, r.text
            session = r.json()


# A session can be started only with the current terms (M3.16).
CONSENT = current_consent().version

DEFAULT_ANSWERS = {
    "fx.q.beta": "yes",
    "fx.q.gamma": "none",
    "fx.q.delta": {"value": 5, "unit": "sample units"},
    "fx.q.duration": {"value": 3, "unit": "days"},
}


@pytest.fixture
def api(client: TestClient) -> Api:
    return Api(client)


@pytest.fixture
def other(client: TestClient) -> Api:
    return Api(client)


@pytest.fixture(scope="session")
def openapi() -> dict[str, Any]:
    """The product's contract: the supplied one with the product's additions (M3.12)."""
    return json.loads((ROOT / "packages" / "contracts" / "openapi.json").read_text())


@pytest.fixture(scope="session")
def supplied_openapi() -> dict[str, Any]:
    """The contract as the handoff supplied it. It is not edited."""
    return json.loads((ROOT / "specs" / "openapi.json").read_text())


@pytest.fixture(scope="session")
def validate_contract(openapi):
    """Checks an answer of the service against a shape of the product's contract."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    registry = Registry().with_resource("urn:feeltriva", Resource(contents=openapi, specification=DRAFT202012))

    def check(schema_name: str, instance: Any) -> None:
        schema = {"$ref": f"urn:feeltriva#/components/schemas/{schema_name}"}
        errors = sorted(
            Draft202012Validator(
                schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
            ).iter_errors(instance),
            key=str,
        )
        assert not errors, f"{schema_name}: " + "; ".join(f"{list(e.path)} {e.message}" for e in errors[:5])

    return check
