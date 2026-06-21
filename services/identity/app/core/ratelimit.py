"""Per-IP, per-route rate limiting (IDN-106).

A lightweight in-memory sliding-window limiter that throttles abusive callers and,
in particular, brute-force attempts against ``/auth/*``. Exceeding the limit yields a
``429`` problem+json response with a ``Retry-After`` header.

Note: state is process-local. Behind multiple replicas this enforces a per-instance
limit; a shared store (e.g. Redis) is the production hardening follow-up.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.errors import problem_response

_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit() -> None:
    """Clear all recorded hits (used by tests)."""
    _hits.clear()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_for(path: str) -> tuple[int, str]:
    if path.startswith("/auth/"):
        return settings.rate_limit_auth_per_minute, "auth"
    return settings.rate_limit_default_per_minute, "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        limit, bucket = _limit_for(request.url.path)
        if limit <= 0:
            return await call_next(request)

        key = f"{_client_ip(request)}:{bucket}"
        now = time.monotonic()
        hits = _hits[key]
        while hits and now - hits[0] >= _WINDOW_SECONDS:
            hits.popleft()

        if len(hits) >= limit:
            retry_after = max(1, int(_WINDOW_SECONDS - (now - hits[0])) + 1)
            return problem_response(
                429,
                detail="Rate limit exceeded; please slow down.",
                instance=request.url.path,
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
