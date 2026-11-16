"""The running API is checked against specs/openapi.json: every operation exists with the
declared operationId, and real responses validate against the contract's schemas."""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from tests.conftest import DEFAULT_ANSWERS, Api


@pytest.fixture(scope="module")
def validate(openapi):
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


def test_every_contract_operation_is_served_with_the_same_operation_id(client, openapi):
    served = {
        (route.path, method): getattr(route, "operation_id", None)
        for route in client.app.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }
    for path, item in openapi["paths"].items():
        for method, operation in item.items():
            assert served.get((path, method.upper())) == operation["operationId"], (method, path)


def test_declared_error_statuses_cover_everything_the_api_returns(openapi):
    declared = {code for item in openapi["paths"].values() for op in item.values() for code in op["responses"]}
    assert {"400", "401", "403", "404", "409", "422", "429", "503"} <= declared


def test_success_responses_match_contract_schemas(api: Api, validate):
    r = api.start({"age_years": 30, "gender_identity": "woman", "clinically_relevant_context": {"k": "v"}})
    assert r.status_code == 201
    session = r.json()
    validate("Session", session)
    sid = session["session_id"]

    session = api.text(sid, 0, "alpha, maybe gamma, and something unmatched").json()
    validate("Session", session)
    session = api.confirm_all(session)
    validate("Session", session)

    question = api.next_question(sid, session["observation_version"]).json()
    validate("Question", question)
    validate("Assessment", api.assess(sid, session["observation_version"]).json())  # needs_clarification

    session = api.answer_all(session, DEFAULT_ANSWERS)
    validate("Session", session)  # includes number, duration and choice values
    validate("Session", api.get(sid).json())
    result = api.assess(sid, session["observation_version"]).json()
    assert result["status"] == "provisional"
    validate("Assessment", result)
    validate("Summary", api.summary(sid, session["observation_version"]).json())
    validate("DeletionReceipt", api.delete(sid).json())


def test_other_assessment_states_match_contract(api: Api, validate):
    urgent = api.start({"age_years": 30}).json()["session_id"]
    api.text(urgent, 0, "escalation marker")
    validate("Assessment", api.assess(urgent, 1).json())
    minor = api.start({"age_years": 12}).json()
    validate("Session", minor)
    validate("Assessment", api.assess(minor["session_id"], 0).json())
    empty = api.start().json()
    validate("Session", empty)  # no demographics supplied: field omitted, not null


def test_error_responses_match_contract(api: Api, other: Api, client, validate):
    sid = api.start({"age_years": 30}).json()["session_id"]
    responses = {
        400: client.post("/v1/sessions", headers=api.headers(None), json={"consent_version": "c"}),
        401: client.get(f"/v1/sessions/{sid}"),
        404: other.get(sid),
        409: api.assess(sid, 7),
        422: client.post("/v1/sessions", headers=api.headers(), json={}),
    }
    for status, r in responses.items():
        assert r.status_code == status
        validate("Error", r.json())
    assert client.get("/v1/unknown-route", headers=api.headers(None)).status_code == 404
    validate("Error", client.get("/v1/unknown-route", headers=api.headers(None)).json())
