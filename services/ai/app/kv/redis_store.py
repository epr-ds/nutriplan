"""The Redis-backed :class:`~app.kv.store.KeyValueStore` adapter.

This is the only module that knows about the ``redis`` driver, and it imports it lazily
in :meth:`from_url` so the package imports cleanly wherever Redis is neither installed nor
running (the test suite injects a duck-typed client instead). The adapter stays thin: it
maps the port onto ``GET`` / ``SET ... EX`` / ``INCRBY`` + ``EXPIRE`` and decodes bytes to
``str`` so callers see the same shape as the in-memory store.
"""

from __future__ import annotations

from typing import Any, Protocol


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str, ex: int | None = ...) -> Any: ...
    def incrby(self, key: str, amount: int) -> int: ...
    def expire(self, key: str, seconds: int) -> Any: ...


class RedisKeyValueStore:
    """Adapt a redis-py-style client to the key-value store port."""

    def __init__(self, client: RedisLike) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisKeyValueStore:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        return cls(redis.Redis.from_url(url, decode_responses=True))

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if ttl_seconds > 0:
            self._client.set(key, value, ex=ttl_seconds)
        else:
            self._client.set(key, value)

    def increment(self, key: str, amount: int, *, ttl_seconds: int) -> int:
        total = int(self._client.incrby(key, amount))
        if total == amount and ttl_seconds > 0:  # first write in this window -> set expiry
            self._client.expire(key, ttl_seconds)
        return total
