"""The consumer, handler, and delivery ports the eventing framework is built on (NTF-201).

Three seams, kept deliberately small:

:class:`DeliveredEvent`
    One message as the broker handed it over -- still raw. It carries the broker's own
    identifier and the delivery attempt, because both are transport facts the domain has no
    business knowing but the dispatcher must act on.

:class:`EventConsumer`
    The transport. Redis Streams is one implementation, an in-process queue is the other,
    and nothing above this port knows which it has. Every method here maps to something a
    consumer group genuinely offers -- there is no method that Redis could not honour.

:class:`EventHandler`
    What a story like NTF-202 plugs in: given a validated envelope, do the thing. A handler
    sees no acks, no delivery ids and no retry counts, so it cannot accidentally take
    responsibility for delivery semantics that belong to the dispatcher.

**The ack contract is the important part of this file.** ``poll`` hands out events that stay
*pending* until :meth:`EventConsumer.ack` is called for them; anything left un-acked is
eligible to come back through :meth:`EventConsumer.reclaim`. That is at-least-once, and it is
not a detail of the Redis adapter -- the in-process adapter reproduces it exactly, or the
dev/CI path would be a more forgiving world than production and every ordering bug would
wait until deploy to appear.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.events.envelope import EventEnvelope


@dataclass(frozen=True, slots=True)
class DeliveredEvent:
    """One raw message off the bus, with the transport facts needed to settle it."""

    delivery_id: str
    """The broker's identifier for this delivery -- a Redis stream entry id.

    Used to ack, and to correlate log lines with ``XPENDING`` output during an incident.
    Note this is *not* the producer's event id: see :mod:`app.events.envelope` for why
    deduplication must key on the latter.
    """

    payload: str
    """The envelope as published, still unparsed -- parsing is the dispatcher's job.

    Kept raw so a payload that cannot be parsed at all can still be parked verbatim. A
    dead-letter entry holding the exact bytes that failed is the only thing that makes the
    failure reproducible; storing a partially-parsed rendering of it would discard the
    evidence along with the event.
    """

    attempt: int = 1
    """How many times the broker has delivered this message, starting at 1.

    Redis maintains this in the pending-entries list, so it survives the death of the
    consumer that was holding the message -- which is exactly the case a retry budget has to
    be able to count.
    """


@runtime_checkable
class EventConsumer(Protocol):
    """A durable, at-least-once subscription to one stream as one consumer group."""

    def ensure_group(self) -> None:
        """Create the consumer group if it does not exist; idempotent.

        Called on startup rather than at build time so constructing a consumer never touches
        the network, which keeps unit tests and dependency wiring free of a live broker.
        """
        ...

    def poll(self, *, count: int, block_ms: int) -> Sequence[DeliveredEvent]:
        """Return up to ``count`` messages not yet delivered to this group.

        Blocks for up to ``block_ms`` waiting for one, then returns empty. Returned messages
        are pending until acked.
        """
        ...

    def reclaim(self, *, min_idle_ms: int, count: int) -> Sequence[DeliveredEvent]:
        """Take over messages another consumer left pending for longer than ``min_idle_ms``.

        This is what makes at-least-once true across a crash. Without it, a consumer killed
        between receiving a message and acking it would strand that message in the pending
        list forever -- delivered once, handled never, and invisible to every liveness check
        the service has.
        """
        ...

    def ack(self, delivery_id: str) -> None:
        """Settle one message, removing it from the pending list for good."""
        ...


@runtime_checkable
class EventHandler(Protocol):
    """Acts on one validated event. Raising means "retry me"."""

    def handle(self, envelope: EventEnvelope) -> None:
        """Do whatever this event calls for.

        Contract: return normally and the delivery is acked. Raise
        :class:`~app.events.errors.EventError` and it is parked as permanently unhandleable.
        Raise anything else and it is redelivered, so a handler must be safe to run twice --
        which for this service means going through
        :class:`~app.application.notification_recorder.NotificationRecorder` rather than
        writing to the store directly.
        """
        ...
