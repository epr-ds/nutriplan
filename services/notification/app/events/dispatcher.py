"""Turning a delivery into an ack, a park, or a redelivery (NTF-201, AC1).

Everything else in this package describes the world; this module decides what to do about
it. One delivery goes through five gates, and each one settles it differently:

===========================  ==========================================================
outcome                      what happens
===========================  ==========================================================
retry budget exhausted       park, then ack -- it has failed ``max_attempts`` times
payload will not parse       park, then ack -- permanent (:class:`MalformedEvent`)
unknown event type           **ack only** -- not our traffic, and not a failure
unsupported version /        park, then ack -- permanent, but a deploy may fix it
  missing required fields
no handler registered        **ack only** -- known event, deliberately not acted on
handler raises ``EventError``  park, then ack -- the handler declared it permanent
handler raises anything else  **no ack** -- transient, so the bus redelivers it
handler returns              ack
===========================  ==========================================================

Two things in that table are worth stating outright, because they are choices rather than
consequences:

**Permanent failures are acked.** Acking looks like admitting success, and it is not: the
event has already been copied into the dead-letter sink by then, so the ack settles the
*delivery*, not the problem. The alternative -- leaving it pending -- does not preserve
anything the sink has not already kept, and guarantees the reclaim pass picks it up on every
cycle from now until someone notices, re-parking it each time. One real failure would
generate an unbounded stream of identical dead-letters and drown the queue it was meant to
alert on.

**Unrecognised exceptions are retryable.** The dispatcher only treats a failure as permanent
when the handler says so by raising :class:`~app.events.errors.EventError`. Anything else --
including an exception type nobody has considered yet -- gets redelivered. The asymmetry is
on purpose: guessing "permanent" on a transient fault silently loses a user's notification,
while guessing "transient" on a permanent one costs a handful of retries and then hits the
budget, which parks it anyway. One mistake is invisible and unrecoverable; the other is loud
and self-correcting.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.events.consumer import DeliveredEvent, EventConsumer, EventHandler
from app.events.dead_letter import DeadLetterSink
from app.events.envelope import EventEnvelope, parse_envelope
from app.events.errors import EventError
from app.events.registry import Compatibility, EventSchemaRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class BatchResult:
    """What one pass over a batch did, for logging and for the worker's own accounting."""

    handled: int = 0
    dropped: int = 0
    dead_lettered: int = 0
    retried: int = 0

    @property
    def total(self) -> int:
        """Every delivery the batch settled one way or another."""
        return self.handled + self.dropped + self.dead_lettered + self.retried

    def __add__(self, other: BatchResult) -> BatchResult:
        """Accumulate results across batches, so the worker can report a running total."""
        return BatchResult(
            handled=self.handled + other.handled,
            dropped=self.dropped + other.dropped,
            dead_lettered=self.dead_lettered + other.dead_lettered,
            retried=self.retried + other.retried,
        )


class EventDispatcher:
    """Applies the settle-or-retry rules to deliveries from one consumer."""

    def __init__(
        self,
        consumer: EventConsumer,
        *,
        registry: EventSchemaRegistry,
        dead_letters: DeadLetterSink,
        handlers: Mapping[str, EventHandler] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._consumer = consumer
        self._registry = registry
        self._dead_letters = dead_letters
        self._handlers: dict[str, EventHandler] = dict(handlers or {})
        self._max_attempts = max(1, max_attempts)

    def register(self, event_type: str, handler: EventHandler) -> None:
        """Route ``event_type`` to ``handler``, refusing to silently replace an existing one.

        Two handlers for one type is a wiring mistake, and the failure mode of allowing it is
        that the second registration wins and the first never runs again -- with no error
        anywhere. NTF-202 registers order handlers through this method.
        """
        if event_type in self._handlers:
            raise ValueError(f"a handler is already registered for {event_type!r}")
        self._handlers[event_type] = handler

    @property
    def handled_types(self) -> tuple[str, ...]:
        """Every event type with a handler, sorted."""
        return tuple(sorted(self._handlers))

    def ensure_subscribed(self) -> None:
        """Create the consumer group if it is not there yet.

        Called once at worker start rather than from the constructor, so building a
        dispatcher -- in a test, or while wiring dependencies -- never opens a connection.
        """
        self._consumer.ensure_group()

    def dispatch(self, delivery: DeliveredEvent) -> BatchResult:
        """Settle exactly one delivery according to the table in the module docstring."""
        if delivery.attempt > self._max_attempts:
            return self._park(
                delivery,
                f"retry budget exhausted after {delivery.attempt} deliveries",
            )

        try:
            envelope = parse_envelope(delivery.payload)
        except EventError as exc:
            return self._park(delivery, str(exc))

        verdict = self._registry.check(envelope)
        if verdict.compatibility is Compatibility.UNKNOWN_TYPE:
            logger.info(
                "notification.event.ignored delivery_id=%s type=%s reason=%s",
                delivery.delivery_id,
                envelope.type,
                verdict.reason,
            )
            return self._drop(delivery)
        if not verdict:
            return self._park(delivery, verdict.reason)

        handler = self._handlers.get(envelope.type)
        if handler is None:
            logger.debug(
                "notification.event.unhandled delivery_id=%s type=%s",
                delivery.delivery_id,
                envelope.type,
            )
            return self._drop(delivery)

        return self._handle(delivery, envelope, handler)

    def dispatch_batch(self, deliveries: Iterable[DeliveredEvent]) -> BatchResult:
        """Settle every delivery in a batch, returning the combined result."""
        result = BatchResult()
        for delivery in deliveries:
            result += self.dispatch(delivery)
        return result

    def poll_once(self, *, count: int, block_ms: int) -> BatchResult:
        """Read one batch of new messages and settle all of them."""
        return self.dispatch_batch(self._consumer.poll(count=count, block_ms=block_ms))

    def reclaim_once(self, *, min_idle_ms: int, count: int) -> BatchResult:
        """Take over messages stranded by a dead consumer and settle all of them."""
        return self.dispatch_batch(self._consumer.reclaim(min_idle_ms=min_idle_ms, count=count))

    def _handle(
        self, delivery: DeliveredEvent, envelope: EventEnvelope, handler: EventHandler
    ) -> BatchResult:
        """Run a handler and settle by what it raised, if anything."""
        try:
            handler.handle(envelope)
        except EventError as exc:
            # The handler itself declared this permanent -- e.g. a data field it needs is
            # absent from an otherwise schema-valid payload.
            return self._park(delivery, f"handler rejected {envelope.type}: {exc}")
        except Exception:
            logger.exception(
                "notification.event.retry delivery_id=%s type=%s attempt=%d",
                delivery.delivery_id,
                envelope.type,
                delivery.attempt,
            )
            # No ack: the delivery stays pending and the reclaim pass will re-serve it.
            return BatchResult(retried=1)

        self._consumer.ack(delivery.delivery_id)
        return BatchResult(handled=1)

    def _drop(self, delivery: DeliveredEvent) -> BatchResult:
        """Ack an event that is not ours to act on, without parking it."""
        self._consumer.ack(delivery.delivery_id)
        return BatchResult(dropped=1)

    def _park(self, delivery: DeliveredEvent, reason: str) -> BatchResult:
        """Send a permanently-failed delivery to the sink, then ack it.

        The ack follows the park, never precedes it: if the sink raises despite its contract,
        the delivery stays pending and gets another chance, which is the right way round.
        Acking first would settle the message and *then* lose it.
        """
        self._dead_letters.park(delivery, reason=reason)
        self._consumer.ack(delivery.delivery_id)
        return BatchResult(dead_lettered=1)
