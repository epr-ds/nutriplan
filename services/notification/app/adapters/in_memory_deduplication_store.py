"""The in-process idempotency store.

The parity partner of the Redis adapter: correct for dev, CI, and a single container, and
useless the moment there are two replicas, since nothing is shared between processes. That
is the same trade the notification store makes, and the same one ``/health/ready`` reports.

Expiry is evaluated against an injected clock rather than swept by a background task, so a
test can advance time and observe a lapsed provisional lease without sleeping. Reads prune
what they walk over, which keeps the dict from growing without bound in a long-lived
process.

A lock makes ``claim`` atomic for the Redis adapter's counterpart reason: the real store gets
its "one claim wins" guarantee from the server evaluating ``SET ... NX`` as a single command,
while this one has a check-then-write that two threads would otherwise both slip through.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from app.adapters.idempotency import IdempotencyWindow
from app.domain.dedupe import Claim, DedupeKey

Clock = Callable[[], float]


class InMemoryDeduplicationStore:
    """A dict-backed deduplication store with the same semantics as the Redis one."""

    def __init__(
        self,
        *,
        window: IdempotencyWindow | None = None,
        clock: Clock = time.time,
    ) -> None:
        self._window = window or IdempotencyWindow()
        self._clock = clock
        self._claims: dict[str, tuple[str, float]] = {}
        # Stands in for the Redis server's per-command atomicity, so a threaded test sees the
        # same "exactly one claim wins" outcome rather than a racy double acquisition.
        self._lock = threading.Lock()

    # -- internals ---------------------------------------------------------------

    @staticmethod
    def _key(key: DedupeKey | str) -> str:
        return str(key)

    def _live_holder(self, key: str) -> str | None:
        """Return the holder if the lease is still valid, dropping it if it has lapsed.

        Not locked itself: every caller holds ``self._lock`` across the read *and* the
        decision that follows it, which is the pair that has to be atomic.
        """
        entry = self._claims.get(key)
        if entry is None:
            return None
        holder, expires_at = entry
        if expires_at <= self._clock():
            del self._claims[key]
            return None
        return holder

    # -- port --------------------------------------------------------------------

    def claim(self, key: DedupeKey | str, holder: str) -> Claim:
        if not self._window.enabled:
            return Claim(acquired=True, holder=holder)

        token = self._key(key)
        with self._lock:
            current = self._live_holder(token)
            if current is not None:
                return Claim(acquired=current == holder, holder=current)
            self._claims[token] = (holder, self._clock() + self._window.provisional)
            return Claim(acquired=True, holder=holder)

    def confirm(self, key: DedupeKey | str, holder: str) -> bool:
        if not self._window.enabled:
            return True
        token = self._key(key)
        with self._lock:
            if self._live_holder(token) != holder:
                return False
            self._claims[token] = (holder, self._clock() + self._window.ttl_seconds)
            return True

    def release(self, key: DedupeKey | str, holder: str) -> bool:
        if not self._window.enabled:
            return False
        token = self._key(key)
        with self._lock:
            if self._live_holder(token) != holder:
                return False
            del self._claims[token]
            return True

    def holder_of(self, key: DedupeKey | str) -> str | None:
        if not self._window.enabled:
            return None
        with self._lock:
            return self._live_holder(self._key(key))
