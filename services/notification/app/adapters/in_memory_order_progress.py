"""The in-process order-progress mark -- the dev/CI twin of the Redis one (NTF-202).

Same contract, same monotonicity, and the same expiry behaviour, because a double that never
forgets would make the store look more reliable in tests than it is in production. The TTL is
honoured against a monotonic-ish clock so a test can prove that an expired mark reports
:data:`~app.domain.order_status.NO_PROGRESS` without waiting a week for it.

Not safe across processes, which is the point of it being the fallback rather than the
default: two replicas each keeping their own idea of an order's progress would announce every
status twice.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.domain.order_status import NO_PROGRESS, OrderStatus, progress_of


@dataclass(slots=True)
class _Mark:
    progress: int
    expires_at: float


class InMemoryOrderProgressStore:
    """A dict-backed order-progress store with the same guarantees as the Redis one."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 604_800,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._clock = clock or time.monotonic
        self._marks: dict[str, _Mark] = {}
        # The Redis adapter gets its atomicity from the server running the script; here the
        # lock is what stands in for it, so a threaded test observes the same monotonicity.
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        """How long a mark survives without further movement on the order."""
        return self._ttl_seconds

    def _live(self, order_id: str) -> _Mark | None:
        mark = self._marks.get(order_id)
        if mark is None:
            return None
        if mark.expires_at <= self._clock():
            del self._marks[order_id]
            return None
        return mark

    # -- port --------------------------------------------------------------------

    def progress_of(self, order_id: str) -> int:
        with self._lock:
            mark = self._live(order_id)
            return NO_PROGRESS if mark is None else mark.progress

    def advance(self, order_id: str, status: OrderStatus) -> bool:
        progress = progress_of(status)
        with self._lock:
            mark = self._live(order_id)
            if mark is not None and mark.progress >= progress:
                return False
            self._marks[order_id] = _Mark(
                progress=progress,
                expires_at=self._clock() + self._ttl_seconds,
            )
            return True

    # -- test affordances --------------------------------------------------------

    def clear(self) -> None:
        """Forget every order -- for tests that need a clean slate between cases."""
        with self._lock:
            self._marks.clear()
