"""MCP tools and REST must be the same service: same results, same guards."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from feeltriva_api.auth import ASSESSMENT_SCOPES, Principal
from feeltriva_mcp.server import build_server
from mcp.server.mcpserver.exceptions import ToolError

from tests.conftest import DEFAULT_ANSWERS, Api

EXPECTED_TOOLS = {
    "start_assessment",
    "get_assessment_session",
    "get_current_assessment",
    "submit_observations",
    "submit_answer",
    "assess_session",
    "get_next_question",
    "get_condition_information",
    "create_consultation_summary",
    "delete_session",
}


class Mcp:
    def __init__(self, container, subject: str | None = None, scopes=ASSESSMENT_SCOPES) -> None:
        self.subject = subject or f"dev:user-{uuid.uuid4().hex[:12]}"
        self.server = build_server(container, lambda: Principal(self.subject, frozenset(scopes)))

    def call(self, tool: str, **arguments: Any) -> Any:
        if tool not in ("get_assessment_session", "get_next_question", "get_condition_information"):
            arguments.setdefault("idempotency_key", uuid.uuid4().hex)
        result = asyncio.run(self.server.call_tool(tool, arguments))
        assert result.is_error is False
        return result.structured_content

    def error(self, tool: str, **arguments: Any) -> dict[str, Any]:
        with pytest.raises(ToolError) as raised:
            self.call(tool, **arguments)
        text = str(raised.value)
        return json.loads(text[text.index("{") :])


def _scrub(value: Any, ids: dict[str, str]) -> Any:
    """Replace per-session identifiers and timestamps so two independent runs can be compared."""
    if isinstance(value, dict):
        return {k: ("<time>" if k == "expires_at" else _scrub(v, ids)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, ids) for v in value]
    if isinstance(value, str):
        try:
            uuid.UUID(value)
        except ValueError:
            return value
        return ids.setdefault(value, f"<id-{len(ids)}>")
    return value


def test_tool_surface_matches_the_contract(container):
    tools = asyncio.run(Mcp(container).server.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        properties = set(tool.input_schema["properties"])
        assert not properties & {"owner_subject", "user_id", "subject", "sql", "url", "command"}, tool.name
    delete = next(t for t in tools if t.name == "delete_session")
    assert "confirm_delete" in delete.input_schema["required"]


def test_full_flow_gives_identical_results_over_rest_and_mcp(container, api: Api):
    mcp = Mcp(container)
    rest_ids: dict[str, str] = {}
    mcp_ids: dict[str, str] = {}
    demographics = {"age_years": 41}

    r = api.start(demographics).json()
    m = mcp.call("start_assessment", consent_version="test-consent-1", demographics=demographics)
    assert _scrub(r, rest_ids) == _scrub(m, mcp_ids)
    rsid, msid = r["session_id"], m["session_id"]

    text = "alpha for a while, no gamma"
    r = api.text(rsid, 0, text).json()
    m = mcp.call("submit_observations", session_id=msid, observation_version=0, text=text)
    assert _scrub(r, rest_ids) == _scrub(m, mcp_ids)

    def confirm(session):
        return [
            {
                "feature_id": o["feature_id"],
                "presence": o["presence"],
                "confirmed": True,
                "supersedes": o["observation_id"],
            }
            for o in session["observations"]
        ]

    r = api.observe(rsid, 1, confirm(r)).json()
    m = mcp.call("submit_observations", session_id=msid, observation_version=1, observations=confirm(m))
    assert _scrub(r, rest_ids) == _scrub(m, mcp_ids)

    while True:
        rq = api.next_question(rsid, r["observation_version"])
        mq = mcp.call("get_next_question", session_id=msid, observation_version=m["observation_version"])["question"]
        if rq.status_code == 204:
            assert mq is None
            break
        assert rq.json() == mq
        answer = DEFAULT_ANSWERS[mq["question_id"]]
        r = api.answer(rsid, r["observation_version"], mq["question_id"], answer).json()
        m = mcp.call(
            "submit_answer",
            session_id=msid,
            observation_version=m["observation_version"],
            question_id=mq["question_id"],
            answer=answer,
        )
        assert _scrub(r, rest_ids) == _scrub(m, mcp_ids)

    version = r["observation_version"]
    ra = api.assess(rsid, version).json()
    ma = mcp.call("assess_session", session_id=msid, observation_version=version)
    assert ra["status"] == "provisional"
    assert _scrub(ra, rest_ids) == _scrub(ma, mcp_ids)
    # The assessment that was made can be read again over either transport, and is the same one (M3.12).
    assert api.client.get(f"/v1/sessions/{rsid}/assessment", headers=api.headers(None)).json() == ra
    assert mcp.call("get_current_assessment", session_id=msid) == ma
    assert (
        api.summary(rsid, version).json()["summary_text"]
        == mcp.call("create_consultation_summary", session_id=msid, observation_version=version)["summary_text"]
    )
    assert _scrub(api.get(rsid).json(), rest_ids) == _scrub(
        mcp.call("get_assessment_session", session_id=msid), mcp_ids
    )

    rd = api.delete(rsid).json()
    md = mcp.call("delete_session", session_id=msid, confirm_delete=True)
    assert (rd["status"], md["status"]) == ("deletion_scheduled", "deletion_scheduled")
    assert mcp.error("get_assessment_session", session_id=msid)["code"] == "session_not_found"


def test_a_session_started_over_rest_continues_over_mcp_for_the_same_caller(container, api: Api):
    mcp = Mcp(container, subject=f"dev:{api.subject}")
    sid = api.start({"age_years": 30}).json()["session_id"]
    assert (
        mcp.call("submit_observations", session_id=sid, observation_version=0, text="alpha")["observation_version"] == 1
    )
    assert api.get(sid).json()["observation_version"] == 1
    # A REST write the MCP client has not seen makes the MCP client's version stale.
    api.confirm_all(api.get(sid).json())
    assert mcp.error("assess_session", session_id=sid, observation_version=1)["code"] == "stale_observation_version"


def test_mcp_cannot_bypass_ownership_versions_question_validation_or_scopes(container, api: Api):
    sid = api.confirm_all(api.text(api.start({"age_years": 30}).json()["session_id"], 0, "alpha").json())["session_id"]
    stranger = Mcp(container)
    for tool, args in (
        ("get_assessment_session", {}),
        ("get_next_question", {"observation_version": 2}),
        ("submit_observations", {"observation_version": 2, "text": "beta"}),
        ("submit_answer", {"observation_version": 2, "question_id": "fx.q.beta", "answer": "yes"}),
        ("assess_session", {"observation_version": 2}),
        ("create_consultation_summary", {"observation_version": 2}),
        ("delete_session", {"confirm_delete": True}),
    ):
        assert stranger.error(tool, session_id=sid, **args)["code"] == "session_not_found", tool

    owner = Mcp(container, subject=f"dev:{api.subject}")
    assert (
        owner.error("submit_answer", session_id=sid, observation_version=2, question_id="fx.q.gamma", answer="none")[
            "code"
        ]
        == "question_not_current"
    )
    assert (
        owner.error("submit_answer", session_id=sid, observation_version=2, question_id="fx.q.beta", answer="perhaps")[
            "code"
        ]
        == "invalid_answer"
    )
    assert owner.error("delete_session", session_id=sid, confirm_delete=False)["code"] == "confirmation_required"
    assert owner.error("get_assessment_session", session_id="not-a-uuid")["code"] == "validation_error"
    secret = "PRIVATE-TEXT"
    invalid = owner.error(
        "submit_observations",
        session_id=sid,
        observation_version=2,
        text=secret,
        observations=[{"feature_id": "fx.signal_beta", "presence": "present", "confirmed": True}],
    )
    assert invalid["code"] == "validation_error" and secret not in json.dumps(invalid)

    read_only = Mcp(container, subject=f"dev:{api.subject}", scopes={"assessment:read"})
    assert read_only.call("get_assessment_session", session_id=sid)["session_id"] == sid
    assert read_only.error("assess_session", session_id=sid, observation_version=2)["code"] == "insufficient_scope"
    assert read_only.error("delete_session", session_id=sid, confirm_delete=True)["code"] == "insufficient_scope"
    assert api.get(sid).json()["observation_version"] == 2  # nothing above changed the session


def test_urgent_state_is_identical_and_pauses_questions_over_mcp(container):
    mcp = Mcp(container)
    sid = mcp.call("start_assessment", consent_version="c")["session_id"]
    session = mcp.call("submit_observations", session_id=sid, observation_version=0, text="escalation marker")
    assert session["state"] == "urgent_handoff"
    assert mcp.call("get_next_question", session_id=sid, observation_version=1) == {"question": None}
    result = mcp.call("assess_session", session_id=sid, observation_version=1)
    assert (result["status"], result["urgency"], result["candidates"]) == ("urgent_handoff", "urgent", [])
