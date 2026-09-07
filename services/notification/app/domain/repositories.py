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

from app.domain.dedupe import Claim, DedupeKey
from app.domain.notification import Notification
from app.domain.preferences import NotificationPreferences


@runtime_checkable
class NotificationRepository(Protocol):
    """Persistence port for the :class:`~app.domain.notification.Notification` record."""

    def add(self, notification: Notification) -> Notification:
        """Persist a notification and index it on its user's feed.

        Re-adding the same id overwrites the record. Deciding whether a notification should
        be written *at all* -- so that a replayed event is a no-op -- belongs one layer
        above this port, in :class:`~app.application.notification_recorder.NotificationRecorder`
        (NTF-103); a store that deduped on its own would have to guess what "the same
        notification" means and would be unable to tell a replay from a legitimate second
        notification of the same type.
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


@runtime_checkable
class DeduplicationStore(Protocol):
    """The idempotency port: who owns a given ``(event, user, type)`` key right now (AC2).

    Claiming is **two-phase**, and the reason is worth stating because a single-phase claim
    looks simpler and is subtly wrong. If a worker claimed a key for the full idempotency
    window and was then hard-killed before writing the notification, the key would sit there
    unowned-but-taken for the whole window; the consumer group would redeliver the event
    within seconds, find the key claimed, treat it as a duplicate, and drop the notification
    permanently. So :meth:`claim` takes the key only for a short provisional lease, and
    :meth:`confirm` extends it to the full window once the notification is safely stored. A
    crash between the two lets the lease lapse on its own and the redelivery succeeds, while
    a genuine duplicate arriving in that gap is still refused.

    Implementations must make :meth:`claim` **atomic** -- a check followed by a separate
    write would let two consumers processing the same redelivered event both win.
    """

    def claim(self, key: DedupeKey | str, holder: str) -> Claim:
        """Take the key for ``holder`` under a short provisional lease.

        Returns an acquired claim naming ``holder`` when the key was free, otherwise a
        refused claim naming whoever holds it, so the caller can resolve the original
        notification rather than merely learning that one exists.
        """
        ...

    def confirm(self, key: DedupeKey | str, holder: str) -> bool:
        """Extend ``holder``'s provisional lease to the full idempotency window.

        Returns ``False`` when ``holder`` no longer owns the key -- its lease lapsed and
        someone else took over -- which the caller should treat as "another delivery is
        authoritative", not as an error.
        """
        ...

    def release(self, key: DedupeKey | str, holder: str) -> bool:
        """Give the key up, but only if ``holder`` still owns it.

        The ownership check is not defensive noise: if a lease lapsed and a redelivery
        re-claimed the key, an unguarded delete here would free *that* claim and let a third
        delivery through -- the exact duplicate this store exists to prevent.
        """
        ...

    def holder_of(self, key: DedupeKey | str) -> str | None:
        """Return the current holder of ``key``, or ``None`` if it is unclaimed."""
        ...


@runtime_checkable
class PreferencesRepository(Protocol):
    """Persistence port for a user's notification opt-outs (NTF-104).

    Unlike notifications, preferences **never expire**. The feed is a rolling window because
    old news stops being useful; a decision to switch something off does not stop being true
    after thirty days. Giving these records the store's retention TTL would quietly re-enable
    every notification a user had muted, at a moment unrelated to anything they did -- so the
    absence of a TTL here is a deliberate asymmetry, not an oversight, and both adapters are
    tested for it.
    """

    def get(self, user_id: uuid.UUID) -> NotificationPreferences | None:
        """Load a user's stored preferences, or ``None`` if they have never set any.

        ``None`` is distinct from "the defaults" at this layer on purpose: only the store can
        say whether a record exists, and collapsing the two here would make it impossible to
        tell a first-time visitor from someone who deliberately reset everything. Callers that
        do not care -- the delivery path, chiefly -- substitute
        :meth:`~app.domain.preferences.NotificationPreferences.defaults` immediately.
        """
        ...

    def save(self, preferences: NotificationPreferences) -> NotificationPreferences:
        """Persist a user's preferences, replacing any previous record, and return them."""
        ...
