"""The Redis Streams consumer-group adapter (NTF-201, AC3).

The only module here that knows the ``redis`` driver, imported lazily in :meth:`from_url` so
the package stays importable wherever Redis is neither installed nor running -- the same
arrangement the publishing side uses.

Commerce ``XADD``s each envelope as a single ``payload`` field (COM-109); this reads it back
with ``XREADGROUP`` under a named consumer group. A *group* rather than a bare ``XREAD``
because the group is what gives us the two properties the story asks for: competing replicas
each get a disjoint slice of the stream, and Redis maintains a pending-entries list so a
message delivered to a consumer that then dies is not lost.

**Where a new group starts, and why it is not the beginning.** The group is created at ``$``
-- the current end of the stream -- never at ``0``. Starting at ``0`` reads as the safer,
lose-nothing option and is the opposite: the first time this service is deployed against a
stream that already holds a month of commerce traffic, it would walk the entire backlog and
emit a notification for every order event in it. Users would be told their long-delivered
orders had just been confirmed, and NTF-103's dedupe could not help, because none of those
events was ever handled and so none of them has a key. The cost of ``$`` is a genuine but
one-time gap: events published before the group first existed are never seen. Every window
after that is covered, because the group persists and its pending list survives restarts --
so an outage of the *consumer* loses nothing, which is the case that actually recurs.

``MKSTREAM`` creates the stream if commerce has not published to it yet, so consumer and
producer can be deployed in either order.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from app.events.backoff import RetrySchedule
from app.events.consumer import DeliveredEvent, ReclaimResult

PAYLOAD_FIELD = "payload"
"""The stream field carrying the JSON envelope. Must match the commerce publisher."""

NEW_MESSAGES = ">"
"""``XREADGROUP``'s "never delivered to this group" cursor."""

STREAM_END = "$"
"""Where a newly created group starts -- see the module docstring."""

BUSYGROUP = "BUSYGROUP"
"""Redis's error prefix for "this consumer group already exists"."""


class RedisStreamsLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> Any: ...
    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = ...,
        block: int | None = ...,
    ) -> Any: ...
    def xpending_range(
        self,
        name: str,
        groupname: str,
        min: str,
        max: str,
        count: int,
        idle: int | None = ...,
    ) -> Any: ...
    def xclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        message_ids: Sequence[str],
    ) -> Any: ...
    def xack(self, name: str, groupname: str, *ids: str) -> Any: ...


class RedisStreamEventConsumer:
    """Consume one Redis stream as one named consumer group."""

    def __init__(
        self,
        client: RedisStreamsLike,
        *,
        stream: str,
        group: str,
        consumer: str,
    ) -> None:
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer

    @classmethod
    def from_url(
        cls, url: str, *, stream: str, group: str, consumer: str
    ) -> RedisStreamEventConsumer:
        """Build a consumer from a ``redis://`` URL, importing the driver lazily."""
        import redis

        return cls(
            redis.Redis.from_url(url, decode_responses=True),
            stream=stream,
            group=group,
            consumer=consumer,
        )

    @property
    def stream(self) -> str:
        """The stream being consumed -- ``NOTIFICATION_ORDER_EVENT_STREAM``."""
        return self._stream

    @property
    def group(self) -> str:
        """The consumer group whose offset and pending list this consumer shares."""
        return self._group

    def ensure_group(self) -> None:
        """Create the group at the end of the stream; tolerate it already existing.

        ``XGROUP CREATE`` errors with ``BUSYGROUP`` when the group is there, which is the
        expected outcome on every start after the first. It is matched on message rather than
        on an exception type because redis-py raises a generic ``ResponseError`` for all
        command errors -- catching that alone would also swallow a genuinely broken stream.
        """
        try:
            self._client.xgroup_create(
                name=self._stream,
                groupname=self._group,
                id=STREAM_END,
                mkstream=True,
            )
        except Exception as exc:
            if BUSYGROUP not in str(exc):
                raise

    def poll(self, *, count: int, block_ms: int) -> Sequence[DeliveredEvent]:
        """Read up to ``count`` new messages, blocking up to ``block_ms`` for the first."""
        response = self._client.xreadgroup(
            groupname=self._group,
            consumername=self._consumer,
            streams={self._stream: NEW_MESSAGES},
            count=count,
            block=block_ms,
        )
        if not response:
            return ()

        delivered: list[DeliveredEvent] = []
        for _stream, entries in response:
            for entry_id, fields in entries:
                delivered.append(DeliveredEvent(entry_id, _payload(fields), attempt=1))
        return tuple(delivered)

    def reclaim(self, *, schedule: RetrySchedule, count: int) -> ReclaimResult:
        """Take over pending messages whose backoff has elapsed; leave the rest pending.

        Two commands rather than ``XAUTOCLAIM`` because the delivery count is the whole
        reason for reclaiming: ``XPENDING`` reports it, ``XAUTOCLAIM`` does not, and without
        it neither the retry budget nor the backoff schedule could be applied to exactly the
        messages that keep killing their consumer.

        ``XPENDING`` is asked for entries idle at least :attr:`RetrySchedule.floor_ms`, which
        is the shortest wait any entry can have. That is a cheap server-side pre-filter, not
        the decision: an entry on its fourth attempt is fetched by it and then found not due,
        because its own wait is sixteen times longer. Doing the coarse filter server-side
        keeps a backlog of deferred entries from being dragged across the wire every sweep.
        """
        pending = self._client.xpending_range(
            name=self._stream,
            groupname=self._group,
            min="-",
            max="+",
            count=count,
            idle=schedule.floor_ms,
        )
        if not pending:
            return ReclaimResult()

        attempts: dict[str, int] = {}
        deferred = 0
        for entry in pending:
            message_id = str(entry["message_id"])
            times_delivered = int(entry["times_delivered"])
            idle_ms = int(entry["time_since_delivered"])
            if not schedule.is_due(
                attempt=times_delivered, idle_ms=idle_ms, delivery_id=message_id
            ):
                deferred += 1
                continue
            attempts[message_id] = times_delivered

        if not attempts:
            return ReclaimResult(deferred=deferred)

        claimed = self._client.xclaim(
            name=self._stream,
            groupname=self._group,
            consumername=self._consumer,
            # The claim re-checks idleness server-side against the shortest wait any entry
            # could have. It is a guard against a race, not a second policy decision: another
            # replica may have claimed the entry between the XPENDING and here, and without
            # the guard both consumers would run the same handler at the same time.
            min_idle_time=schedule.floor_ms,
            message_ids=list(attempts),
        )

        delivered: list[DeliveredEvent] = []
        for entry_id, fields in claimed or ():
            if not fields:
                # The entry is in the pending list but no longer in the stream: someone
                # ``XDEL``ed it, or it aged out under a MAXLEN trim. There is nothing left to
                # handle, and leaving it pending would have every future reclaim pass pick up
                # the same tombstone, so settle it and move on.
                self.ack(entry_id)
                continue
            # XCLAIM increments the delivery counter, so the attempt this delivery represents
            # is one past what XPENDING reported a moment ago.
            attempt = attempts.get(str(entry_id), 0) + 1
            delivered.append(DeliveredEvent(entry_id, _payload(fields), attempt=attempt))
        return ReclaimResult(deliveries=tuple(delivered), deferred=deferred)

    def ack(self, delivery_id: str) -> None:
        """Remove one message from the group's pending list."""
        self._client.xack(self._stream, self._group, delivery_id)


def _payload(fields: dict[str, str]) -> str:
    """Extract the envelope text from a stream entry's fields.

    An entry without a ``payload`` field is something other than a commerce event -- a
    hand-written ``XADD``, or a producer that changed the field name. Rather than skip it
    silently, the whole field map is returned as JSON so the dispatcher's parse fails on it
    and it is parked *with its actual contents*, which is what makes the mistake diagnosable.
    """
    payload = fields.get(PAYLOAD_FIELD)
    if isinstance(payload, str):
        return payload
    return json.dumps(fields)
