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
handler raises anything else  **no ack** -- transient, so the bus redelivers it after backoff
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

**Replay is the same chain with the settling removed** (NTF-204). :meth:`EventDispatcher.replay`
runs a parked payload back through parse, registry check and handler, and deliberately does
*not* ack (the delivery was acked when it was parked -- there is nothing left on the bus to
settle) and does *not* park on failure (the entry is already in the queue; re-parking it would
overwrite the original reason with an identical one and make a replay that keeps failing look
like a fresh failure each time). It reports what happened and leaves the queue alone, which is
what makes replaying safe to run twice.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.events.backoff import RetrySchedule
from app.events.consumer import DeliveredEvent, EventConsumer, EventHandler
from app.events.dead_letter import DeadLetterQueue
from app.events.envelope import EventEnvelope, parse_envelope
from app.events.errors import EventError
from app.events.metrics import EventMetrics, Outcome
from app.events.registry import Compatibility, EventSchemaRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5


class NoHandlerRegistered(EventError):
    """Raised by :meth:`EventDispatcher.replay` when nothing would act on the event.

    Only reachable through replay. The live path *acks* an event with no handler, because a
    producer emitting types this service does not care about is normal traffic -- but an entry
    already sitting in the dead-letter queue is there because it failed, and reporting "replay
    succeeded" for an event that nothing ran would let an operator delete it believing it had
    been dealt with.
    """


@dataclass(frozen=True, slots=True)
class BatchResult:
    """What one pass over a batch did, for logging and for the worker's own accounting."""

    handled: int = 0
    dropped: int = 0
    dead_lettered: int = 0
    retried: int = 0
    deferred: int = 0
    """Pending entries seen but left alone because their backoff has not elapsed (NTF-204)."""

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
            deferred=self.deferred + other.deferred,
        )


class EventDispatcher:
    """Applies the settle-or-retry rules to deliveries from one consumer."""

    def __init__(
        self,
        consumer: EventConsumer,
        *,
        registry: EventSchemaRegistry,
        dead_letters: DeadLetterQueue,
        handlers: Mapping[str, EventHandler] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        schedule: RetrySchedule | None = None,
        metrics: EventMetrics | None = None,
    ) -> None:
        self._consumer = consumer
        self._registry = registry
        self._dead_letters = dead_letters
        self._handlers: dict[str, EventHandler] = dict(handlers or {})
        self._max_attempts = max(1, max_attempts)
        self._schedule = schedule or RetrySchedule(base_ms=60_000)
        self._metrics = metrics or EventMetrics()

    @property
    def metrics(self) -> EventMetrics:
        """The counters this dispatcher has been keeping (NTF-204, AC3)."""
        return self._metrics

    @property
    def dead_letters(self) -> DeadLetterQueue:
        """The queue parked events go to -- what the replayer and the CLI drain."""
        return self._dead_letters

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
            return self._drop(delivery, event_type=envelope.type)
        if not verdict:
            return self._park(delivery, verdict.reason, event_type=envelope.type)

        handler = self._handlers.get(envelope.type)
        if handler is None:
            logger.debug(
                "notification.event.unhandled delivery_id=%s type=%s",
                delivery.delivery_id,
                envelope.type,
            )
            return self._drop(delivery, event_type=envelope.type)

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

    def reclaim_once(self, *, count: int, schedule: RetrySchedule | None = None) -> BatchResult:
        """Take over messages whose backoff has elapsed and settle all of them.

        Entries the schedule holds back are reported as ``deferred`` rather than being
        invisible: a pending list that is not shrinking looks the same whether backoff is
        working or the consumer has stopped, and this is the number that tells them apart.
        """
        outcome = self._consumer.reclaim(schedule=schedule or self._schedule, count=count)
        self._metrics.increment(Outcome.DEFERRED, count=outcome.deferred)
        return self.dispatch_batch(outcome.deliveries) + BatchResult(deferred=outcome.deferred)

    def replay(self, payload: str) -> str:
        """Re-run one parked payload through the full chain, settling nothing.

        Returns the event type that was handled. Raises :class:`~app.events.errors.EventError`
        for a payload that is still permanently bad -- which is the expected outcome when a
        replay is attempted before the fix is deployed -- and lets a transient failure escape
        as whatever the handler raised, so an operator replaying against a down dependency is
        told that rather than being shown a misleading "permanently failed".
        """
        envelope = parse_envelope(payload)
        verdict = self._registry.check(envelope)
        if not verdict:
            raise EventError(verdict.reason)
        handler = self._handlers.get(envelope.type)
        if handler is None:
            raise NoHandlerRegistered(f"no handler is registered for {envelope.type}")
        handler.handle(envelope)
        return envelope.type

    def _handle(
        self, delivery: DeliveredEvent, envelope: EventEnvelope, handler: EventHandler
    ) -> BatchResult:
        """Run a handler and settle by what it raised, if anything."""
        try:
            handler.handle(envelope)
        except EventError as exc:
            # The handler itself declared this permanent -- e.g. a data field it needs is
            # absent from an otherwise schema-valid payload.
            return self._park(
                delivery, f"handler rejected {envelope.type}: {exc}", event_type=envelope.type
            )
        except Exception:
            logger.exception(
                "notification.event.retry delivery_id=%s type=%s attempt=%d",
                delivery.delivery_id,
                envelope.type,
                delivery.attempt,
            )
            # No ack: the delivery stays pending and the reclaim pass will re-serve it once
            # its backoff has elapsed.
            self._metrics.increment(Outcome.RETRIED, event_type=envelope.type)
            return BatchResult(retried=1)

        self._consumer.ack(delivery.delivery_id)
        self._metrics.increment(Outcome.HANDLED, event_type=envelope.type)
        return BatchResult(handled=1)

    def _drop(self, delivery: DeliveredEvent, *, event_type: str | None = None) -> BatchResult:
        """Ack an event that is not ours to act on, without parking it."""
        self._consumer.ack(delivery.delivery_id)
        self._metrics.increment(Outcome.DROPPED, event_type=event_type)
        return BatchResult(dropped=1)

    def _park(
        self, delivery: DeliveredEvent, reason: str, *, event_type: str | None = None
    ) -> BatchResult:
        """Send a permanently-failed delivery to the queue, then ack it.

        The ack follows the park, never precedes it: if the queue raises despite its contract,
        the delivery stays pending and gets another chance, which is the right way round.
        Acking first would settle the message and *then* lose it.
        """
        self._dead_letters.park(delivery, reason=reason)
        self._consumer.ack(delivery.delivery_id)
        self._metrics.increment(Outcome.DEAD_LETTERED, event_type=event_type)
        return BatchResult(dead_lettered=1)
