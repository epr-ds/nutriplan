"""The persistence port for notifications.

The application depends on this Protocol, never on Redis. Two adapters implement it (an
in-process one for dev/CI and tests, a Redis one for anything with more than one replica)
and a shared contract suite runs against both, so "works in tests" and "works in
production" mean the same thing.

Every method is **owner-scoped**: a caller must present the ``user_id`` alongside the
notification id, so an unknown id and someone else's id are indistinguishable and the feed
API cannot leak another user's notifications by enumerating UUIDs.

The store is a **rolling window, not an archive** (AC2). Records expire, so any lookup can
legitimately return ``None`` for an id that existed a moment ago; callers translate that
into a 404 rather than treating it as an error.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from app.domain.notification import Notification


@runtime_checkable
class NotificationRepository(Protocol):
    """Persistence port for the :class:`~app.domain.notification.Notification` record."""

    def add(self, notification: Notification) -> Notification:
        """Persist a notification and index it on its user's feed.

        Re-adding the same id overwrites the record; the deterministic dedupe that makes a
        replayed event a no-op is NTF-103's job, one layer above this port.
        """
        ...

    def get(self, notification_id: uuid.UUID, *, user_id: uuid.UUID) -> Notification | None:
        """Load one of ``user_id``'s notifications, or ``None`` if absent/expired/not theirs."""
        ...

    def update(self, notification: Notification) -> Notification | None:
        """Persist a whole-record change, or return ``None`` if the record has expired.

        This backs both read-state changes (NTF-105) and delivery-status changes (NTF-303).
        It never resurrects an expired record: a store that silently re-created one would
        make an expired notification reappear in the feed with a stale timestamp.
        """
        ...

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Return the user's notifications, newest first (AC3).

        A page may come back shorter than ``limit`` when entries in the requested slice have
        expired since they were indexed -- the index is pruned lazily, so a read can observe
        an id whose record is already gone. Callers paginate by ``offset``, not by assuming
        a full page means more results.
        """
        ...

    def count_unread(self, user_id: uuid.UUID) -> int:
        """Return how many unread notifications the user has inside the retention window."""
        ...
