"""The Redis key scheme -- one place that decides what lives under which key.

Three key shapes back the store::

    {ns}:v1:n:{notification_id}   -> the JSON record            (string, EX retention)
    {ns}:v1:u:{user_id}:feed     -> every id, newest first      (sorted set)
    {ns}:v1:u:{user_id}:unread   -> the unread subset           (sorted set)

and a fourth carries the idempotency claims (NTF-103)::

    {ns}:v1:d:{type}:{digest}    -> the notification id that handled this event (string, EX)

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
