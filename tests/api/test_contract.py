"""The running API is checked against the product's contract, packages/contracts/openapi.json: every operation
exists with the declared operationId, and real responses validate against the contract's schemas. The product's
contract is the supplied one (specs/openapi.json) with additions; nothing supplied is changed."""

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
    # M3.12: the current assessment can be read again, and is the one that was made.
    again = api.client.get(f"/v1/sessions/{sid}/assessment", headers=api.headers(None))
    assert again.status_code == 200
    validate("Assessment", again.json())
    assert again.json() == result
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


def test_the_supplied_contract_is_whole_and_unchanged_inside_the_products_contract(openapi, supplied_openapi):
    """Additions only (M3.12): every supplied operation and every supplied field is there as it was supplied."""
    for path, item in supplied_openapi["paths"].items():
        assert openapi["paths"][path] == item, path
    for name, schema in supplied_openapi["components"]["schemas"].items():
        ours = openapi["components"]["schemas"][name]
        assert ours.get("required", []) == schema.get("required", []), name
        for field, shape in schema.get("properties", {}).items():
            assert ours["properties"][field] == shape, f"{name}.{field}"
        assert {key: value for key, value in ours.items() if key != "properties"} == {
            key: value for key, value in schema.items() if key != "properties"
        }, name
        # What was added to a supplied shape is optional, so a caller that sends or reads only what was supplied
        # is served as before.
        assert not (set(ours.get("properties", {})) - set(schema.get("properties", {}))) & set(ours.get("required", []))
    added = {
        (path, method): operation["operationId"]
        for path, item in openapi["paths"].items()
        for method, operation in item.items()
        if method not in supplied_openapi["paths"].get(path, {})
    }
    assert added == {
        ("/v1/sessions/{session_id}/assessment", "get"): "getCurrentAssessment",
        ("/v1/conditions/{disease_id}", "get"): "getConditionInformation",
    }


def test_an_observation_carries_its_name_the_answer_in_words_and_what_is_known_about_the_symptom(api: Api, validate):
    session = api.start({"age_years": 30}).json()
    sid = session["session_id"]
    session = api.text(sid, 0, "I have alpha").json()
    alpha = session["observations"][0]
    # The name of the item is given in words beside its internal value.
    assert (alpha["feature_id"], alpha["display_name"]) == ("fx.signal_alpha", "Fixture signal alpha (sample)")
    described = api.observe(
        sid,
        session["observation_version"],
        [
            {
                "feature_id": "fx.signal_alpha",
                "presence": "present",
                "confirmed": True,
                "supersedes": alpha["observation_id"],
                "location": "left side (sample)",
                "pattern": "comes and goes (sample)",
                "triggers": "after a pretend walk",
                "relieving_factors": "a pretend rest",
            }
        ],
    )
    assert described.status_code == 200, described.text
    session = described.json()
    validate("Session", session)
    kept = session["observations"][0]
    assert (kept["location"], kept["pattern"], kept["triggers"], kept["relieving_factors"]) == (
        "left side (sample)",
        "comes and goes (sample)",
        "after a pretend walk",
        "a pretend rest",
    )
    too_long = api.observe(
        sid,
        session["observation_version"],
        [
            {
                "feature_id": "fx.signal_alpha",
                "presence": "present",
                "confirmed": True,
                "supersedes": kept["observation_id"],
                "location": "x" * 201,
            }
        ],
    )
    assert too_long.status_code == 422
    session = api.answer_all(session, DEFAULT_ANSWERS)
    validate("Session", session)
    by_item = {o["feature_id"]: o for o in session["observations"]}
    # The stored value stays an internal value; the words are given beside it (BUG-009, now for any later reader).
    assert (by_item["fx.signal_gamma"]["value"], by_item["fx.signal_gamma"]["value_label"]) == ("none", "None of these")
    assert by_item["fx.signal_delta"]["value_label"] == "5 sample units"
    assert by_item["fx.context_duration"]["value_label"] == "3 days"
    assert "value_label" not in by_item["fx.signal_beta"]  # a yes or no has nothing more to say
    text = api.summary(sid, session["observation_version"]).json()["summary_text"]
    assert "location: left side (sample)" in text and "relieving factors: a pretend rest" in text


def test_the_current_assessment_is_read_only_while_the_details_stand(api: Api, other: Api, client, validate):
    session = api.start({"age_years": 30}).json()
    sid = session["session_id"]

    def current(who: Api = api):
        return client.get(f"/v1/sessions/{sid}/assessment", headers=who.headers(None))

    assert client.get(f"/v1/sessions/{sid}/assessment").status_code == 401
    missing = current()
    assert (missing.status_code, missing.json()["code"]) == (404, "no_current_assessment")
    validate("Error", missing.json())
    session = api.answer_all(api.confirm_all(api.text(sid, 0, "I have alpha").json()), DEFAULT_ANSWERS)
    made = api.assess(sid, session["observation_version"]).json()
    assert current().json() == made
    assert current(other).status_code == 404  # another caller is told nothing
    # Once a detail changes, the assessment made before is not the current one any more.
    beta = next(o for o in session["observations"] if o["feature_id"] == "fx.signal_beta")
    changed = api.observe(
        sid,
        session["observation_version"],
        [
            {
                "feature_id": "fx.signal_beta",
                "presence": "absent",
                "confirmed": True,
                "supersedes": beta["observation_id"],
            }
        ],
    ).json()
    assert current().json()["code"] == "no_current_assessment"
    again = api.assess(sid, changed["observation_version"]).json()
    assert current().json() == again and again["assessment_id"] != made["assessment_id"]


def test_the_written_list_of_review_routes_is_what_the_service_serves(client):
    """M3.12: the review workspace's routes are written down from the running service, and the file is current.
    When this fails after a route was added or changed on purpose: `uv run python -m feeltriva_api.contract`."""
    from feeltriva_api import contract

    served = contract.internal_contract(client.app)
    assert contract.PATH.read_text(encoding="utf-8") == contract.render(served)
    operations = {(path, method) for path, item in served["paths"].items() for method in item}
    assert ("/internal/v1/review/decisions", "post") in operations and len(operations) > 40
    # Nothing of the assessment API is in it, and nothing internal is in the assessment API's contract.
    assert all(path.startswith("/internal/") for path in served["paths"])
