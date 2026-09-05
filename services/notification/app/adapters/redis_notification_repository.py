"""The Redis-backed notification store.

This is the only module that speaks Redis commands. It maps the port onto:

* ``SET ... EX`` / ``GET`` / ``MGET`` for records,
* ``ZADD`` / ``ZREVRANGE`` / ``ZCOUNT`` for the two per-user indexes (AC3),
* ``ZREMRANGEBYSCORE`` + ``ZREMRANGEBYRANK`` for the retention sweep (AC2).

Two design points are worth stating outright.

**Writes are pipelined in a transaction.** A notification's record and its two index entries
must land together; if the record were written and the index entry lost, the notification
would be invisible forever. ``MULTI``/``EXEC`` makes the three-key write atomic.

**Reads tolerate a dangling index entry.** A record carries its own ``EX`` while a sorted-set
member cannot, so an index can legitimately point at a record that has already expired. The
read path skips such ids and removes the stale pointers it walked over, rather than raising
or fabricating an empty notification. This is also why a page can come back shorter than the
requested limit -- documented on the port.

The ``redis`` driver is imported lazily in :meth:`from_url`, so this package imports cleanly
where Redis is neither installed nor running and the tests can inject a duck-typed client.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from app.adapters import codec
from app.adapters.keys import NotificationKeys
from app.adapters.retention import RetentionPolicy
from app.domain.notification import Notification

Clock = Callable[[], float]


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def mget(self, keys: Iterable[str]) -> list[Any]: ...
    def zrevrange(self, key: str, start: int, end: int) -> list[Any]: ...
    def zcount(self, key: str, min_score: Any, max_score: Any) -> int: ...
    def zrem(self, key: str, *members: str) -> int: ...
    def pipeline(self, transaction: bool = ...) -> Any: ...


class RedisNotificationRepository:
    """Adapt a redis-py-style client to the notification persistence port."""

    def __init__(
        self,
        client: RedisLike,
        *,
        keys: NotificationKeys | None = None,
        policy: RetentionPolicy | None = None,
        clock: Clock = time.time,
    ) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()
        self._policy = policy or RetentionPolicy()
        self._clock = clock

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        keys: NotificationKeys | None = None,
        policy: RetentionPolicy | None = None,
        clock: Clock = time.time,
    ) -> RedisNotificationRepository:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys, policy=policy, clock=clock)

    # -- internals ---------------------------------------------------------------

    @staticmethod
    def _text(value: Any) -> str | None:
        """Normalize a redis-py reply to ``str`` whether or not decoding is enabled."""
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    def _sweep(self, pipe: Any, index_key: str, now: float) -> None:
        """Queue the age and length trims for one index onto ``pipe``."""
        if self._policy.expires:
            pipe.zremrangebyscore(index_key, "-inf", self._policy.horizon(now))
            pipe.expire(index_key, self._policy.ttl_seconds)
        if self._policy.bounded:
            # ZREVRANGE ranks newest-first, so everything at rank >= max_entries is surplus.
            pipe.zremrangebyrank(index_key, 0, -(self._policy.max_entries + 1))

    def _load(self, ids: list[str], *, user_id: uuid.UUID, index_key: str) -> list[Notification]:
        """Fetch records for ``ids``, dropping (and un-indexing) any that have expired."""
        if not ids:
            return []
        raw_records = self._client.mget([self._keys.record(member) for member in ids])

        found: list[Notification] = []
        dangling: list[str] = []
        for member, raw in zip(ids, raw_records, strict=True):
            text = self._text(raw)
            if text is None:
                dangling.append(member)
                continue
            notification = codec.decode(text)
            if notification.user_id == user_id:
                found.append(notification)
        if dangling:
            self._client.zrem(index_key, *dangling)
            self._client.zrem(self._keys.unread(user_id), *dangling)
        return found

    # -- port --------------------------------------------------------------------

    def add(self, notification: Notification) -> Notification:
        now = self._clock()
        score = notification.created_at.timestamp()
        if self._policy.is_expired(score, now=now):
            return notification  # already outside the window; see the in-memory adapter
        feed_key = self._keys.feed(notification.user_id)
        unread_key = self._keys.unread(notification.user_id)

        pipe = self._client.pipeline(transaction=True)
        record_key = self._keys.record(notification.id)
        encoded = codec.encode(notification)
        if self._policy.expires:
            # The lease runs from creation, not from this write: replaying an old event
            # (which NTF-201 explicitly must tolerate) would otherwise hand an ancient
            # notification a full fresh window and resurrect it at the top of the feed.
            remaining = self._policy.ttl_seconds - (now - score)
            pipe.set(record_key, encoded, ex=max(1, int(remaining)))
        else:
            pipe.set(record_key, encoded)
        pipe.zadd(feed_key, {str(notification.id): score})
        if notification.is_read:
            pipe.zrem(unread_key, str(notification.id))
        else:
            pipe.zadd(unread_key, {str(notification.id): score})
        self._sweep(pipe, feed_key, now)
        self._sweep(pipe, unread_key, now)
        pipe.execute()
        return notification

    def get(self, notification_id: uuid.UUID, *, user_id: uuid.UUID) -> Notification | None:
        raw = self._text(self._client.get(self._keys.record(notification_id)))
        if raw is None:
            return None
        notification = codec.decode(raw)
        return notification if notification.user_id == user_id else None

    def update(self, notification: Notification) -> Notification | None:
        if self._client.get(self._keys.record(notification.id)) is None:
            return None
        return self.add(notification)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        if limit <= 0:
            return []
        offset = max(offset, 0)
        index_key = self._keys.index_for(user_id, unread_only=unread_only)
        members = [
            member
            for member in (
                self._text(value)
                for value in self._client.zrevrange(index_key, offset, offset + limit - 1)
            )
            if member is not None
        ]
        return self._load(members, user_id=user_id, index_key=index_key)

    def count_unread(self, user_id: uuid.UUID) -> int:
        # Counting by score rather than ZCARD keeps the badge honest between retention
        # sweeps: an unread notification that has aged out is already excluded here.
        floor = f"({self._policy.horizon(self._clock())}" if self._policy.expires else "-inf"
        return int(self._client.zcount(self._keys.unread(user_id), floor, "+inf"))
