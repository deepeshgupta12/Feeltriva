"""Consent before a session starts (M3.16): the terms and their version, no session without the current version,
the separate choice about improving the product, taking the agreement back, and the 30 days conversations are kept."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from feeltriva_api import consent, retention
from feeltriva_api.models import Session, SessionObservation
from sqlalchemy import select

from tests.conftest import CONSENT, Api

# The wording each version stands for. A change of the wording without a new version fails here: a person who
# agreed to a version agreed to exactly these words.
WORDING = {"consent-in-en-draft-1": "398581eafc00e4c999eb2ee4748a05dd68c48af062070bb829dc7ab7efd00d4f"}


def test_the_terms_are_served_with_their_version_and_without_the_writers_notes(client, api: Api, validate_contract):
    assert client.get("/v1/consent").status_code == 401
    served = client.get("/v1/consent", headers=api.headers(None))
    assert served.status_code == 200
    terms = served.json()
    validate_contract("Consent", terms)
    assert terms["version"] == CONSENT == consent.current().version
    assert "note" not in terms
    # A draft is said to be a draft; the choice about improving the product is described apart from the terms.
    assert terms["status"] == "draft" and terms["training"]["label"] and terms["acknowledgement"]
    wording = hashlib.sha256(json.dumps(terms, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert WORDING[terms["version"]] == wording, "the wording changed: give the terms a new version"


def test_no_session_is_started_without_an_agreement_to_the_current_terms(client, api: Api, validate_contract):
    def start(**body):
        return client.post("/v1/sessions", headers=api.headers(), json=body)

    refused = start(consent_version="an-earlier-version")
    assert (refused.status_code, refused.json()["code"]) == (409, "consent_version_not_current")
    validate_contract("Error", refused.json())
    assert start().status_code == 422  # no version at all
    before = datetime.now(UTC)
    started = start(consent_version=CONSENT, demographics={"age_years": 30})
    assert started.status_code == 201
    session = started.json()
    validate_contract("Session", session)
    # What was agreed to, and when, is kept with the session.
    accepted = datetime.fromisoformat(session["consent_accepted_at"])
    assert session["consent_version"] == CONSENT and before - timedelta(seconds=5) <= accepted <= datetime.now(UTC)
    # The choice about improving the product is separate and is not made unless the person makes it.
    assert session["training_consent"] is False
    chosen = start(consent_version=CONSENT, training_consent=True).json()
    assert chosen["training_consent"] is True
    assert client.get(f"/v1/sessions/{chosen['session_id']}", headers=api.headers(None)).json()["training_consent"]


def test_taking_the_agreement_back_removes_the_conversation(api: Api, owner_db):
    session = api.start({"age_years": 30}).json()
    sid = session["session_id"]
    api.text(sid, 0, "I have alpha")
    receipt = api.delete(sid)
    assert receipt.status_code == 200 and receipt.json()["receipt_id"].startswith("del_")
    assert api.get(sid).status_code == 404
    with owner_db.transaction(None, role="migration") as tx:
        kept = tx.scalars(select(SessionObservation).where(SessionObservation.session_id == uuid.UUID(sid))).all()
        assert kept == []


def test_a_conversation_is_deleted_when_it_is_older_than_thirty_days(api: Api, owner_db):
    old, recent = (api.start({"age_years": 30}).json()["session_id"] for _ in range(2))
    api.text(old, 0, "I have alpha")
    # The old one is given a start in the year 2000, and the purge is run as on a day of that year, so that no
    # row of another test is old enough to be touched.
    long_ago = datetime(2000, 1, 1, tzinfo=UTC)
    with owner_db.transaction(None, role="migration") as tx:
        tx.get(Session, uuid.UUID(old)).created_at = long_ago
    day_30 = long_ago + timedelta(days=30)
    assert retention.due(owner_db, now=day_30 - timedelta(hours=1)) == 0  # 30 days are not over yet
    assert retention.purge(owner_db, now=day_30 - timedelta(hours=1)) == 0
    assert retention.due(owner_db, now=day_30 + timedelta(hours=1)) == 1
    assert retention.purge(owner_db, now=day_30 + timedelta(hours=1)) == 1
    with owner_db.transaction(None, role="migration") as tx:
        assert tx.get(Session, uuid.UUID(old)) is None
        assert tx.scalars(select(SessionObservation).where(SessionObservation.session_id == uuid.UUID(old))).all() == []
        assert tx.get(Session, uuid.UUID(recent)) is not None
    assert api.get(old).status_code == 404 and api.get(recent).status_code == 200


def test_the_same_holds_over_mcp(container):
    from tests.mcp.test_mcp_parity import Mcp

    mcp = Mcp(container)
    assert mcp.call("get_consent") == consent.current().shown()
    refused = mcp.error("start_assessment", consent_version="an-earlier-version")
    assert refused["code"] == "consent_version_not_current"
    started = mcp.call("start_assessment", consent_version=CONSENT, training_consent=True)
    assert (started["consent_version"], started["training_consent"]) == (CONSENT, True)
