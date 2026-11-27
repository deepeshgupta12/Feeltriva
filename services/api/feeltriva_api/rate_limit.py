"""A limit on how many requests one caller may make in a stretch of time (M3.13).

Counted per verified caller, over a sliding window: a caller who has made `limit` requests in the last
`window_seconds` is refused with 429, the standard error body and `Retry-After`, the number of seconds until the
oldest of those requests leaves the window. Other callers are not affected.

The count is held in this process. That is enough for one process; several processes behind one address each
count for themselves, so the effective limit is then several times the configured one. A shared count needs a
store they all reach, which belongs to deployment (M0.10).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from .errors import ApiError


class RateLimited(ApiError):
    """Too many requests from one caller. `retry_after` is in whole seconds, at least 1."""

    def __init__(self, retry_after: int) -> None:
        unit = "second" if retry_after == 1 else "seconds"
        super().__init__(
            429,
            "rate_limited",
            f"Too many requests. Try again in {retry_after} {unit}.",
            retryable=True,
        )
        self.retry_after = retry_after


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit, self.window = limit, float(window_seconds)
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._checks = 0

    @property
    def enabled(self) -> bool:
        return self.limit > 0 and self.window > 0

    def check(self, subject: str) -> None:
        """Count one request of this caller, or refuse it when the caller is at the limit."""
        if not self.enabled:
            return
        now = self._clock()
        with self._lock:
            self._checks += 1
            if self._checks % 1000 == 0:  # callers who have gone quiet are forgotten
                for other in [key for key, times in self._seen.items() if not times or times[-1] <= now - self.window]:
                    del self._seen[other]
            times = self._seen.setdefault(subject, deque())
            while times and times[0] <= now - self.window:
                times.popleft()
            if len(times) >= self.limit:
                raise RateLimited(max(1, math.ceil(times[0] + self.window - now)))
            times.append(now)
