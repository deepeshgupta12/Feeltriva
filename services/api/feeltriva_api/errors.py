from __future__ import annotations


class ApiError(Exception):
    """Carries the public Error body. `message` must never contain health content."""

    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def not_found() -> ApiError:
    # Same response for missing, deleted and not-owned sessions: existence is not disclosed.
    return ApiError(404, "session_not_found", "Session not found.")


def stale_version(current: int) -> ApiError:
    return ApiError(
        409,
        "stale_observation_version",
        f"Observation version is out of date. Refresh the session (current version {current}) and resubmit.",
    )
