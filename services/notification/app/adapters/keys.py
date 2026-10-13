"""The Redis key scheme -- one place that decides what lives under which key.

Three key shapes back the store::

    {ns}:v1:n:{notification_id}   -> the JSON record            (string, EX retention)
    {ns}:v1:u:{user_id}:feed     -> every id, newest first      (sorted set)
    {ns}:v1:u:{user_id}:unread   -> the unread subset           (sorted set)

and a fourth carries the idempotency claims (NTF-103)::

    {ns}:v1:d:{type}:{digest}    -> the notification id that handled this event (string, EX)

and the dead-letter queue is a fifth pair (NTF-204)::

    {ns}:v1:dlq                  -> every parked delivery id, newest first (sorted set)
    {ns}:v1:dlq:e:{delivery_id}  -> the parked entry's JSON record   (string, EX retention)

The two per-user sorted sets are the "indexed for feed queries" half of AC3: listing a
page is a ``ZREVRANGE`` slice plus an ``MGET``, and the unread badge is a ``ZCOUNT`` --
both O(log N + page) rather than a scan over the user's history.

The unread index is a sorted set rather than a plain set on purpose. Scoring it by the same
creation time as the feed means the retention sweep can trim it with the same
``ZREMRANGEBYSCORE`` horizon, and an unread count can exclude aged-out entries by score even
before the sweep has run -- a plain ``SCARD`` would drift upward forever as old unread
records expired underneath it.

Every key is namespaced (``NOTIFICATION_REDIS_NAMESPACE``) so several environments can share
one Redis, and versioned (``v1``) so changing the stored shape is a clean cache-miss rather
than a silent misread of the old format.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

SCHEMA_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class NotificationKeys:
    """Builds the namespaced, versioned keys for one logical dataset."""

    namespace: str = "notification"

    @property
    def prefix(self) -> str:
        """The shared ``{namespace}:{version}`` prefix every key starts with."""
        return f"{self.namespace}:{SCHEMA_VERSION}"

    def record(self, notification_id: uuid.UUID | str) -> str:
        """The key holding one notification's JSON record."""
        return f"{self.prefix}:n:{notification_id}"

    def feed(self, user_id: uuid.UUID | str) -> str:
        """The sorted set indexing all of a user's notifications by creation time."""
        return f"{self.prefix}:u:{user_id}:feed"

    def unread(self, user_id: uuid.UUID | str) -> str:
        """The sorted set indexing the unread subset of a user's notifications."""
        return f"{self.prefix}:u:{user_id}:unread"

    def index_for(self, user_id: uuid.UUID | str, *, unread_only: bool) -> str:
        """The index a feed query should read: the unread subset, or everything."""
        return self.unread(user_id) if unread_only else self.feed(user_id)

    def dedupe(self, key: object) -> str:
        """The key holding the idempotency claim for one (event, user, type) triple.

        Sharing the namespace and version with the records is intentional: a schema bump
        that invalidates stored notifications must invalidate the dedupe keys pointing at
        them too, or a replay would be suppressed on behalf of a record no longer readable.
        """
        return f"{self.prefix}:d:{key}"

    def preferences(self, user_id: uuid.UUID | str) -> str:
        """The key holding one user's notification preferences (NTF-104).

        Deliberately *not* under the ``u:{user_id}:`` prefix the feed indexes use. Those keys
        all carry the feed's retention TTL and are swept together; preferences must outlive
        every notification they govern, so they are kept clearly apart from anything a
        retention sweep touches.
        """
        return f"{self.prefix}:p:{user_id}"

    def order_progress(self, order_id: str) -> str:
        """The key holding how far along one order has been announced (NTF-202).

        Keyed by *order*, not by user, because the question it answers is about the order's
        lifecycle. Commerce puts exactly one user on an order, so nothing is lost, and a
        key that named both would be unreachable from an event that carried only one of them.
        """
        return f"{self.prefix}:o:{order_id}"

    @property
    def dead_letters(self) -> str:
        """The sorted set indexing every parked event by when it failed (NTF-204).

        A single global index rather than one per user or per type: a dead letter may be a
        payload so broken that neither could be determined, and an index keyed on something
        the entry might not have would silently fail to record exactly the worst failures.
        """
        return f"{self.prefix}:dlq"

    def dead_letter(self, delivery_id: str) -> str:
        """The key holding one parked event's JSON record (NTF-204).

        Keyed by *delivery* id, not event id: two different stream entries can carry the same
        envelope after a replay, and an operator acting on the queue is acting on the entry
        the broker actually failed to settle.
        """
        return f"{self.prefix}:dlq:e:{delivery_id}"
