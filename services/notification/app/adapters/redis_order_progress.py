"""The Redis-backed order-progress mark (NTF-202, AC3).

The whole adapter is one Lua script. "Store this rank if it is higher than what is there" has
to be a single atomic step, because the read-then-write version has a race with real
consequences: two workers handling ``preparing`` and ``in_transit`` for the same order both
read ``confirmed``, both write, and whichever lands second wins. If that is ``preparing``, the
mark now sits *behind* the order's true position, and the next stale event -- exactly the
thing this store exists to catch -- sails through and tells the user their order is being
prepared after it has left the kitchen.

``SET ... GT`` would express this natively but was added in Redis 7.0 for ``EXPIRE``, not for
values; there is no value-comparing ``SET``. So the comparison is scripted, which Redis runs
atomically, and the script also (re)sets the TTL so an order that keeps moving keeps its mark
alive for the full window rather than expiring mid-lifecycle from the first status it reached.

The stored value is the rank, not the status name. Ranks are what the comparison needs, and a
name would force the script to carry the ordering -- putting the domain's most consequential
piece of ordering knowledge in a string inside a string, where nothing type-checks it.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.adapters.keys import NotificationKeys
from app.domain.order_status import NO_PROGRESS, OrderStatus, progress_of

_ADVANCE_IF_GREATER = """
local current = redis.call('get', KEYS[1])
if current and tonumber(current) >= tonumber(ARGV[1]) then
    return 0
end
redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def eval(self, script: str, numkeys: int, *args: Any) -> Any: ...


class RedisOrderProgressStore:
    """Adapt a redis-py-style client to the order-progress port."""

    def __init__(
        self,
        client: RedisLike,
        *,
        keys: NotificationKeys | None = None,
        ttl_seconds: int = 604_800,
    ) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()
        self._ttl_seconds = max(1, int(ttl_seconds))

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        keys: NotificationKeys | None = None,
        ttl_seconds: int = 604_800,
    ) -> RedisOrderProgressStore:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys, ttl_seconds=ttl_seconds)

    @property
    def ttl_seconds(self) -> int:
        """How long a mark survives without further movement on the order."""
        return self._ttl_seconds

    # -- port --------------------------------------------------------------------

    def progress_of(self, order_id: str) -> int:
        stored = self._client.get(self._keys.order_progress(order_id))
        if stored is None:
            return NO_PROGRESS
        text = stored if isinstance(stored, str) else stored.decode("utf-8")
        try:
            return int(text)
        except ValueError:
            # A value we cannot read is worse than no value: it would make every subsequent
            # comparison raise inside the consumer. Treat it as unset and let the next
            # advance overwrite it -- the cost is at most one re-announced status.
            return NO_PROGRESS

    def advance(self, order_id: str, status: OrderStatus) -> bool:
        moved = self._client.eval(
            _ADVANCE_IF_GREATER,
            1,
            self._keys.order_progress(order_id),
            progress_of(status),
            self._ttl_seconds,
        )
        return bool(moved)
