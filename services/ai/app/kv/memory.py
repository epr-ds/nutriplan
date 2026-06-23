"""An in-process :class:`~app.kv.store.KeyValueStore` for dev, CI, and tests.

It honours TTLs against an injected clock (so expiry is exercised without sleeping) and
keeps a fixed window on counters by setting the expiry only when a key is first created.
It is single-process state, so production shares one Redis instead -- but every layer
above depends only on the port, so swapping the two changes nothing else.
"""

from __future__ import annotations

import time

from app.kv.store import Clock


class InMemoryKeyValueStore:
    """A dict-backed store with lazy, clock-driven expiry."""

    def __init__(self, *, clock: Clock = time.time) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[str, float | None]] = {}

    def _live(self, key: str) -> tuple[str, float | None] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        _, expiry = entry
        if expiry is not None and self._clock() >= expiry:
            del self._entries[key]
            return None
        return entry

    def _expiry_for(self, ttl_seconds: int) -> float | None:
        return self._clock() + ttl_seconds if ttl_seconds > 0 else None

    def get(self, key: str) -> str | None:
        entry = self._live(key)
        return None if entry is None else entry[0]

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._entries[key] = (value, self._expiry_for(ttl_seconds))

    def increment(self, key: str, amount: int, *, ttl_seconds: int) -> int:
        entry = self._live(key)
        if entry is None:
            self._entries[key] = (str(amount), self._expiry_for(ttl_seconds))
            return amount
        total = int(entry[0]) + amount
        self._entries[key] = (str(total), entry[1])  # keep the original window
        return total
