"""The key-value store port shared by the response cache and the budget guard.

Both AIA-105 concerns need the same small surface: read a value, write one with a TTL,
and atomically add to a counter that expires after a window. Keeping that surface as a
port lets Redis be one adapter among others (an in-process one backs dev/CI and tests),
so nothing above this seam imports a driver or assumes a server is running.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

Clock = Callable[[], float]
"""Returns the current time as epoch seconds; injected so TTLs are testable."""


@runtime_checkable
class KeyValueStore(Protocol):
    """A minimal string store with per-key expiry and atomic counters."""

    def get(self, key: str) -> str | None:
        """Return the stored value, or ``None`` when absent or expired."""
        ...

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        """Store ``value`` under ``key``; ``ttl_seconds <= 0`` means no expiry."""
        ...

    def increment(self, key: str, amount: int, *, ttl_seconds: int) -> int:
        """Atomically add ``amount`` to a counter, returning the new total.

        The TTL is applied only when the counter is first created, so a fixed window
        does not slide forward on every increment.
        """
        ...
