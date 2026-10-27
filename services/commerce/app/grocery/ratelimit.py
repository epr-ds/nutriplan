"""Per-provider rate limiting for grocery provider calls (COM-409).

A grocery provider that answers slowly or is flaky should not absorb unlimited calls from a
bursting app: each provider carries a token bucket (capacity + refill rate) and callers that
arrive without a token are throttled. The gateway use case is the cross-provider search fan-out,
which skips a throttled provider exactly like an unavailable one rather than failing the whole
request.
"""

from __future__ import annotations

import time


class ProviderRateLimiter:
    """Token-bucket rate limiter, one bucket per provider id."""

    def __init__(self, *, capacity: int, refill_seconds: float) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_seconds <= 0:
            raise ValueError("refill_seconds must be positive")
        self.capacity = capacity
        self.refill_seconds = refill_seconds
        self._tokens: dict[str, float] = {}
        self._updated: dict[str, float] = {}

    def acquire(self, provider_id: str) -> bool:
        """Try to take one token for ``provider_id``; return False when the bucket is empty."""
        now = time.monotonic()
        tokens = self._tokens.get(provider_id, self.capacity)
        last = self._updated.get(provider_id, now)
        elapsed = now - last
        if elapsed > 0:
            tokens = min(self.capacity, tokens + elapsed / self.refill_seconds)
        if tokens >= 1:
            self._tokens[provider_id] = tokens - 1
            self._updated[provider_id] = now
            return True
        self._updated[provider_id] = now
        return False
