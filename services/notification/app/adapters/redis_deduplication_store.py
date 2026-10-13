"""The Redis-backed idempotency store (AC2).

``SET key holder NX EX provisional`` is the whole mechanism: Redis decides the winner in a
single atomic command, so two consumers handling the same redelivered event cannot both
believe they are first. Everything else here exists to make the *edges* of that command
behave.

**A refused claim needs the holder, which takes a second round trip.** ``SET NX`` reports
only that it failed. The follow-up ``GET`` can legitimately come back empty when the key
expires in the gap between the two commands, and treating that as "no holder" would report a
duplicate with nothing to point at. We retry the claim once instead: the key is genuinely
free at that point, so the retry is the correct outcome rather than a papered-over race.

**Releasing is a compare-and-delete, not a delete.** Under a lapsed provisional lease
another delivery may already own the key; an unguarded ``DEL`` would free *its* claim and let
a third delivery through -- manufacturing the duplicate this store exists to prevent. The
check and the delete have to be one operation, so they run as a Lua script, the same
ownership guard Redlock uses for locks.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.adapters.idempotency import IdempotencyWindow
from app.adapters.keys import NotificationKeys
from app.domain.dedupe import Claim, DedupeKey

_RELEASE_IF_HOLDER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_EXTEND_IF_HOLDER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str, *, nx: bool = ..., ex: int | None = ...) -> Any: ...
    def eval(self, script: str, numkeys: int, *args: Any) -> Any: ...


class RedisDeduplicationStore:
    """Adapt a redis-py-style client to the deduplication port."""

    def __init__(
        self,
        client: RedisLike,
        *,
        keys: NotificationKeys | None = None,
        window: IdempotencyWindow | None = None,
    ) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()
        self._window = window or IdempotencyWindow()

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        keys: NotificationKeys | None = None,
        window: IdempotencyWindow | None = None,
    ) -> RedisDeduplicationStore:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys, window=window)

    # -- internals ---------------------------------------------------------------

    @staticmethod
    def _text(value: Any) -> str | None:
        """Normalize a redis-py reply to ``str`` whether or not decoding is enabled."""
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    def _key(self, key: DedupeKey | str) -> str:
        return self._keys.dedupe(key)

    # -- port --------------------------------------------------------------------

    def claim(self, key: DedupeKey | str, holder: str) -> Claim:
        if not self._window.enabled:
            return Claim(acquired=True, holder=holder)

        redis_key = self._key(key)
        for _ in range(2):
            if self._client.set(redis_key, holder, nx=True, ex=self._window.provisional):
                return Claim(acquired=True, holder=holder)
            current = self._text(self._client.get(redis_key))
            if current is not None:
                return Claim(acquired=current == holder, holder=current)
            # The key expired between the SET and the GET, so it is free again: loop and
            # take it properly rather than reporting a duplicate with no holder to name.
        return Claim(acquired=False, holder=holder)

    def confirm(self, key: DedupeKey | str, holder: str) -> bool:
        if not self._window.enabled:
            return True
        extended = self._client.eval(
            _EXTEND_IF_HOLDER, 1, self._key(key), holder, self._window.ttl_seconds
        )
        return bool(extended)

    def release(self, key: DedupeKey | str, holder: str) -> bool:
        if not self._window.enabled:
            return False
        removed = self._client.eval(_RELEASE_IF_HOLDER, 1, self._key(key), holder)
        return bool(removed)

    def holder_of(self, key: DedupeKey | str) -> str | None:
        if not self._window.enabled:
            return None
        return self._text(self._client.get(self._key(key)))
