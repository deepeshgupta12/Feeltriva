"""The limit on requests per caller (M3.13): the 429 answer with Retry-After, other callers unaffected, the same
limit for a tool call over MCP."""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from fastapi.testclient import TestClient
from feeltriva_api.main import create_app
from feeltriva_api.rate_limit import RateLimited, RateLimiter

from tests.conftest import Api


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_caller_is_refused_at_the_limit_until_the_oldest_request_leaves_the_window():
    clock = Clock()
    limiter = RateLimiter(3, 60, clock)
    for seconds in (0, 10, 20):
        clock.now = 1000 + seconds
        limiter.check("a")
    clock.now = 1025
    with pytest.raises(RateLimited) as refused:
        limiter.check("a")
    # The first request was made at 1000 and leaves the window at 1060: 35 seconds from now.
    assert (refused.value.status, refused.value.code, refused.value.retryable, refused.value.retry_after) == (
        429,
        "rate_limited",
        True,
        35,
    )
    assert refused.value.message == "Too many requests. Try again in 35 seconds."
    limiter.check("b")  # another caller is not affected
    clock.now = 1059.5
    with pytest.raises(RateLimited) as almost:
        limiter.check("a")
    assert almost.value.retry_after == 1 and almost.value.message.endswith("in 1 second.")
    clock.now = 1060.5
    limiter.check("a")  # the oldest request has left; a refused request was never counted
    with pytest.raises(RateLimited) as next_one:
        limiter.check("a")
    assert next_one.value.retry_after == 10  # the request made at 1010 leaves at 1070
    # Switched off, nothing is refused.
    off = RateLimiter(0, 60, clock)
    for _ in range(50):
        off.check("a")


@pytest.fixture
def limited(settings, container):
    """The same service behind a limit of three requests a minute, with a clock the test moves."""
    clock = Clock()
    held = dataclasses.replace(container, limiter=RateLimiter(3, 60, clock))
    with_cors = settings.model_copy(update={"cors_allowed_origins": "http://localhost:5173"})
    return TestClient(create_app(with_cors, held), raise_server_exceptions=False), clock, held


def test_the_fourth_request_of_a_caller_gets_429_with_retry_after_and_nobody_else_is_affected(limited):
    client, clock, _container = limited
    one, other = Api(client), Api(client)
    missing = f"/v1/sessions/{uuid.uuid4()}"
    for _ in range(3):
        assert client.get(missing, headers=one.headers(None)).status_code == 404
    clock.now += 12
    refused = client.get(missing, headers={**one.headers(None), "Origin": "http://localhost:5173"})
    assert refused.status_code == 429
    body = refused.json()
    assert set(body) == {"code", "message", "retryable", "request_id"}  # the standard error body
    assert (body["code"], body["retryable"]) == ("rate_limited", True)
    assert refused.headers["Retry-After"] == "48" and "48 seconds" in body["message"]
    # A browser lets the web app read only the headers the service names.
    assert "Retry-After" in refused.headers["access-control-expose-headers"]
    # A request that changes something is refused in the same way, before anything is done.
    started = one.start({"age_years": 30})
    assert (started.status_code, started.headers["Retry-After"]) == (429, "48")
    # Another caller, the review routes and the health check are not affected.
    assert client.get(missing, headers=other.headers(None)).status_code == 404
    reviewer = Api(client, subject="limit-check", token="dev-reviewer:limit-check")
    for _ in range(5):
        assert client.get("/internal/v1/review/working-sets", headers=reviewer.headers(None)).status_code == 200
    assert client.get("/healthz").status_code == 200
    # A request without a verified caller is refused as before and counts against nobody.
    assert client.get(missing).status_code == 401
    # When the oldest request has left the window the caller is served again.
    clock.now += 49
    assert client.get(missing, headers=one.headers(None)).status_code == 404


def test_a_tool_call_over_mcp_counts_against_the_same_limit(limited):
    from tests.mcp.test_mcp_parity import Mcp

    _client, _clock, container = limited
    mcp = Mcp(container)
    for _ in range(3):
        assert mcp.error("get_assessment_session", session_id=str(uuid.uuid4()))["code"] == "session_not_found"
    refused = mcp.error("get_assessment_session", session_id=str(uuid.uuid4()))
    assert (refused["code"], refused["retryable"]) == ("rate_limited", True)
    assert refused["message"] == "Too many requests. Try again in 60 seconds."
    # Another caller's tool calls go on.
    assert Mcp(container).error("get_assessment_session", session_id=str(uuid.uuid4()))["code"] == "session_not_found"
