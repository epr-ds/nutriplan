"""Per-user rate limiting for the AI edge (AIA-804).

An in-process sliding-window limiter that throttles an authenticated caller per route, so a
single account cannot spend the service's LLM budget in a loop. The gateway is the primary
place for this policy; enforcing it here as well is defence-in-depth, in the same spirit as
the local JWT verification in :mod:`app.api.deps`.

The limit is per ``(user, route)`` so a burst against one endpoint does not consume another's
allowance. State is process-local: behind multiple replicas this enforces a per-instance
limit, and a shared store (e.g. Redis, which the token budget already uses) is the production
follow-up.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit() -> None:
    """Clear all recorded hits (used by tests)."""
    _hits.clear()


def _bucket(path: str) -> str:
    """The route a request belongs to, so limits are enforced per endpoint.

    ``/ai/recommendations`` buckets as ``recommendations``; anything outside ``/ai`` falls
    back to its last path segment so the limiter is still meaningful if it is ever mounted
    elsewhere.
    """
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "ai":
        return parts[1]
    return parts[-1] if parts else "root"


class RateLimitExceeded(Exception):
    """Raised when a caller has exhausted the allowance for a route in the window."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


def check_rate_limit(
    user_id: str,
    path: str,
    *,
    limit: int,
    window_seconds: float = WINDOW_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Record a hit for ``user_id`` on ``path``, or raise :class:`RateLimitExceeded`.

    A non-positive ``limit`` disables the check, mirroring the config flag. The clock is
    injectable so a test can advance time and observe a window lapse without sleeping.
    """
    if limit <= 0:
        return

    key = f"{user_id}:{_bucket(path)}"
    now = clock()
    hits = _hits[key]
    while hits and now - hits[0] >= window_seconds:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
        raise RateLimitExceeded(retry_after)

    hits.append(now)
