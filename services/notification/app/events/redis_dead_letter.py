"""The Redis-backed dead-letter queue (NTF-204, AC2).

Same shape as the notification feed, for the same reasons: a sorted set indexes the entries by
when they failed, and each entry's JSON record lives under its own key with a TTL. A plain
Redis list would be a smaller amount of code and could not do the two things the story asks
for -- fetch one entry by id to inspect it, and remove one entry after replaying it -- without
an O(N) walk of the whole queue.

**Bounded twice, by count and by age.** The queue is capped at ``max_entries`` and every record
carries a TTL, and neither bound alone is enough. A producer stuck in a loop fills the queue in
minutes, so the count cap is what keeps a broken producer from becoming a memory incident; a
single unnoticed failure would otherwise sit there forever, so the TTL is what keeps the queue
from accumulating a year of events nobody is ever going to replay. The TTL is long -- weeks --
because a dead letter that expires is evidence destroyed, and the only thing worse than a full
dead-letter queue is one that quietly emptied itself before anyone looked.

**Eviction drops the oldest.** That is the opposite of what a "keep the first failure, it is
the most diagnostic" argument would suggest, and it is deliberate. A full dead-letter queue
means an incident is in progress; the entries an operator needs are the ones describing what is
failing *now*, not a fortnight-old entry that happened to arrive first. The first failure is
still in the log, which is where the very first thing this queue does with an event is put it.

**The index is pruned lazily on read.** A record can expire while its index member remains, so
a listing that found an id with no record removes the member as it goes. Pruning on write
instead would mean every ``park`` paid for a scan of the whole index, on the error path, which
is the one place in the system with least margin to spend.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from app.adapters.keys import NotificationKeys
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import DEFAULT_CAPACITY, DeadLetter, summarize

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 1_209_600
"""Two weeks -- long enough to survive a holiday weekend plus the deploy that fixes the cause."""


class RedisDeadLetterLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def set(self, name: str, value: str, ex: int | None = ...) -> Any: ...
    def get(self, name: str) -> Any: ...
    def delete(self, *names: str) -> Any: ...
    def zadd(self, name: str, mapping: dict[str, float]) -> Any: ...
    def zrem(self, name: str, *values: str) -> Any: ...
    def zcard(self, name: str) -> Any: ...
    def zrange(self, name: str, start: int, end: int, desc: bool = ...) -> Any: ...


class RedisDeadLetterQueue:
    """Adapt a redis-py-style client to the dead-letter queue port."""

    def __init__(
        self,
        client: RedisDeadLetterLike,
        *,
        keys: NotificationKeys | None = None,
        max_entries: int = DEFAULT_CAPACITY,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()
        self._max_entries = max(1, int(max_entries))
        self._ttl_seconds = max(1, int(ttl_seconds))

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        keys: NotificationKeys | None = None,
        max_entries: int = DEFAULT_CAPACITY,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> RedisDeadLetterQueue:
        """Build a queue from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys, max_entries=max_entries, ttl_seconds=ttl_seconds)

    @property
    def ttl_seconds(self) -> int:
        """How long a parked entry survives before it ages out."""
        return self._ttl_seconds

    @property
    def max_entries(self) -> int:
        """How many entries the queue holds before evicting the oldest."""
        return self._max_entries

    # -- port --------------------------------------------------------------------

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        """Store the failed delivery, logging it first and swallowing any storage failure.

        The log line comes first and unconditionally, because it is the only part of parking
        that cannot itself fail. If Redis is down -- which is a plausible reason the handler
        failed in the first place -- the payload is still recorded somewhere a human can reach
        it, and the exception is contained rather than allowed to break the dispatcher's error
        path (see the port's contract).
        """
        logger.error(
            "notification.event.dead_lettered delivery_id=%s attempt=%d reason=%s payload=%s",
            delivery.delivery_id,
            delivery.attempt,
            reason,
            delivery.payload,
        )
        entry = DeadLetter.of(delivery, reason=reason)
        try:
            self._client.set(
                self._keys.dead_letter(entry.delivery_id),
                json.dumps(_encode(entry)),
                ex=self._ttl_seconds,
            )
            self._client.zadd(
                self._keys.dead_letters,
                {entry.delivery_id: entry.failed_at.timestamp()},
            )
            self._evict_overflow()
        except Exception:
            logger.exception(
                "notification.event.dead_letter_store_failed delivery_id=%s",
                delivery.delivery_id,
            )

    def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[DeadLetter]:
        start = max(0, offset)
        stop = start + max(0, limit) - 1
        if stop < start:
            return ()
        ids = self._client.zrange(self._keys.dead_letters, start, stop, desc=True) or ()
        entries: list[DeadLetter] = []
        for delivery_id in ids:
            entry = self._read(_decode_text(delivery_id))
            if entry is not None:
                entries.append(entry)
        return tuple(entries)

    def get(self, delivery_id: str) -> DeadLetter | None:
        return self._read(delivery_id)

    def depth(self) -> int:
        return int(self._client.zcard(self._keys.dead_letters) or 0)

    def remove(self, delivery_id: str) -> bool:
        removed = int(self._client.zrem(self._keys.dead_letters, delivery_id) or 0)
        self._client.delete(self._keys.dead_letter(delivery_id))
        return removed > 0

    def purge(self) -> int:
        ids = [
            _decode_text(value)
            for value in self._client.zrange(self._keys.dead_letters, 0, -1) or ()
        ]
        if ids:
            self._client.delete(*(self._keys.dead_letter(entry_id) for entry_id in ids))
        self._client.delete(self._keys.dead_letters)
        return len(ids)

    # -- internals ---------------------------------------------------------------

    def _read(self, delivery_id: str) -> DeadLetter | None:
        """Load one record, pruning the index member if the record has aged out."""
        stored = self._client.get(self._keys.dead_letter(delivery_id))
        if stored is None:
            self._client.zrem(self._keys.dead_letters, delivery_id)
            return None
        try:
            return _decode(json.loads(_decode_text(stored)))
        except (TypeError, ValueError, KeyError):
            # A record we cannot read is indistinguishable from one that is not there, and
            # leaving it indexed would have every listing trip over it forever.
            logger.warning("notification.event.dead_letter_unreadable delivery_id=%s", delivery_id)
            self._client.zrem(self._keys.dead_letters, delivery_id)
            return None

    def _evict_overflow(self) -> None:
        """Trim the oldest entries once the queue is over its cap, records included."""
        overflow = self.depth() - self._max_entries
        if overflow <= 0:
            return
        oldest = self._client.zrange(self._keys.dead_letters, 0, overflow - 1) or ()
        ids = [_decode_text(value) for value in oldest]
        if not ids:
            return
        self._client.zrem(self._keys.dead_letters, *ids)
        self._client.delete(*(self._keys.dead_letter(entry_id) for entry_id in ids))


def _encode(entry: DeadLetter) -> dict[str, Any]:
    """Render a parked entry as the JSON object stored under its key."""
    return {
        "deliveryId": entry.delivery_id,
        "payload": entry.payload,
        "attempt": entry.attempt,
        "reason": entry.reason,
        "failedAt": entry.failed_at.isoformat(),
        "eventType": entry.event_type,
        "eventId": entry.event_id,
    }


def _decode(raw: Any) -> DeadLetter:
    """Rebuild a parked entry from its stored JSON object."""
    if not isinstance(raw, dict):
        raise ValueError(f"dead-letter record is a {type(raw).__name__}, expected an object")
    payload = str(raw["payload"])
    # The summary is recomputed when absent rather than defaulted to ``None``: a record
    # written by an older build has no ``eventType`` field, and a listing that showed those
    # entries as unparseable would be lying about why they are in the queue.
    event_type = raw.get("eventType")
    event_id = raw.get("eventId")
    if event_type is None and event_id is None:
        event_type, event_id = summarize(payload)
    return DeadLetter(
        delivery=DeliveredEvent(
            str(raw["deliveryId"]), payload, attempt=int(raw.get("attempt", 1))
        ),
        reason=str(raw.get("reason", "")),
        failed_at=_failed_at(raw.get("failedAt")),
        event_type=event_type,
        event_id=event_id,
    )


def _failed_at(value: Any) -> datetime:
    """Parse the stored timestamp, falling back to now for a record that lost it."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(UTC)


def _decode_text(value: Any) -> str:
    """Return a Redis reply as text, whether the client decodes responses or not."""
    return value if isinstance(value, str) else bytes(value).decode("utf-8")
