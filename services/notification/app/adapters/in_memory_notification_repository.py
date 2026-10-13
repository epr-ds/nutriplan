"""An in-process notification store for dev, CI, and tests.

It is not a simplified stand-in: it honours the same retention policy, the same
newest-first ordering (including Redis's ``(score, member)`` tie-break), the same
owner-scoping, and the same lazy pruning as the Redis adapter, and it stores records as
**encoded JSON** rather than as live objects. That last choice matters -- it means the codec
runs on the dev path too, so a payload that could not survive a round-trip fails locally
instead of only in production.

Its one honest difference is scope: this is single-process state, so it must not back more
than one replica. Everything above the port is unaffected by the swap.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from app.adapters import codec
from app.adapters.retention import RetentionPolicy
from app.domain.enums import NotificationChannel
from app.domain.notification import Notification

Clock = Callable[[], float]
"""Current time as epoch seconds; injected so retention is exercised without sleeping."""

Index = dict[str, dict[str, float]]
"""user id -> {notification id: creation score}, mirroring a per-user sorted set."""


class InMemoryNotificationRepository:
    """A dict-backed :class:`~app.domain.repositories.NotificationRepository`."""

    def __init__(
        self,
        *,
        policy: RetentionPolicy | None = None,
        clock: Clock = time.time,
    ) -> None:
        self._policy = policy or RetentionPolicy()
        self._clock = clock
        self._records: dict[str, str] = {}
        self._created: dict[str, float] = {}
        self._feed: Index = {}
        self._unread: Index = {}

    # -- internals ---------------------------------------------------------------

    def _live_record(self, notification_id: str) -> str | None:
        """Return the stored JSON, dropping it first if it has aged out."""
        created = self._created.get(notification_id)
        if created is None:
            return None
        if self._policy.is_expired(created, now=self._clock()):
            self._records.pop(notification_id, None)
            self._created.pop(notification_id, None)
            return None
        return self._records.get(notification_id)

    def _prune(self, index: Index, user_id: str) -> dict[str, float]:
        """Drop aged-out and over-cap members from one user's index."""
        members = index.setdefault(user_id, {})
        if self._policy.expires:
            horizon = self._policy.horizon(self._clock())
            for member in [m for m, score in members.items() if score <= horizon]:
                del members[member]
        if self._policy.bounded and len(members) > self._policy.max_entries:
            for member, _ in self._ordered(members)[self._policy.max_entries :]:
                del members[member]
        return members

    @staticmethod
    def _ordered(members: dict[str, float]) -> list[tuple[str, float]]:
        """Newest first, tie-broken by descending member -- Redis ``ZREVRANGE`` order."""
        return sorted(members.items(), key=lambda item: (item[1], item[0]), reverse=True)

    def _index(self, *, unread_only: bool) -> Index:
        return self._unread if unread_only else self._feed

    # -- port --------------------------------------------------------------------

    def add(self, notification: Notification) -> Notification:
        key = str(notification.id)
        user = str(notification.user_id)
        score = notification.created_at.timestamp()
        if self._policy.is_expired(score, now=self._clock()):
            # Storing it would be pointless -- every read filters it out immediately -- and
            # skipping keeps the two adapters honest about *when* a record's lease starts.
            return notification

        self._records[key] = codec.encode(notification)
        self._created[key] = score

        if not notification.targets(NotificationChannel.IN_APP):
            # Stored, but not part of the in-app feed: a push-only notification still needs a
            # record (the push adapter renders from it and NTF-303 records receipts against
            # it) while having no business appearing in a feed it does not target. The
            # removals matter for ``update``, where a notification's channels can narrow.
            self._feed.get(user, {}).pop(key, None)
            self._unread.get(user, {}).pop(key, None)
            return notification

        self._prune(self._feed, user)[key] = score
        unread = self._prune(self._unread, user)
        if notification.is_read:
            unread.pop(key, None)
        else:
            unread[key] = score

        # Re-apply the length cap now that a member has been added. An id evicted here stays
        # readable by ``get`` until it ages out, exactly as in Redis: trimming a sorted set
        # does not delete the record key it points at.
        self._prune(self._feed, user)
        self._prune(self._unread, user)
        return notification

    def get(self, notification_id: uuid.UUID, *, user_id: uuid.UUID) -> Notification | None:
        raw = self._live_record(str(notification_id))
        if raw is None:
            return None
        notification = codec.decode(raw)
        return notification if notification.user_id == user_id else None

    def update(self, notification: Notification) -> Notification | None:
        key = str(notification.id)
        if self._live_record(key) is None:
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
        user = str(user_id)
        members = self._prune(self._index(unread_only=unread_only), user)
        window = self._ordered(members)[max(offset, 0) : max(offset, 0) + limit]

        found: list[Notification] = []
        for member, _ in window:
            raw = self._live_record(member)
            if raw is None:  # record expired ahead of its index entry -> drop the pointer
                members.pop(member, None)
                self._feed.get(user, {}).pop(member, None)
                self._unread.get(user, {}).pop(member, None)
                continue
            notification = codec.decode(raw)
            if notification.user_id == user_id:
                found.append(notification)
        return found

    def count_unread(self, user_id: uuid.UUID) -> int:
        return len(self._prune(self._unread, str(user_id)))
