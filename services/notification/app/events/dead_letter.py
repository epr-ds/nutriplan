"""Where an event goes when it cannot be handled and retrying will not help (NTF-201).

This is a **seam, not the queue**. NTF-204 owns the durable dead-letter store, its backoff
policy and its replay path; what NTF-201 needs is somewhere for the dispatcher to send a
permanently-failed event so that "park it" is a real branch with real tests, rather than a
``TODO`` that quietly drops messages until the later story lands.

The default sink logs at ``error`` and keeps the event in memory. Logging is not durability
and is not pretending to be -- but it does mean that on the day a malformed event arrives
before NTF-204 ships, the payload is in the log where someone can find it, instead of gone.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from app.events.consumer import DeliveredEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """A permanently-failed delivery, kept with enough context to act on later."""

    delivery: DeliveredEvent
    reason: str
    """Why it was parked, in words an operator can act on -- not an exception repr."""

    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def delivery_id(self) -> str:
        """The broker id of the parked delivery."""
        return self.delivery.delivery_id


@runtime_checkable
class DeadLetterSink(Protocol):
    """Accepts an event the consumer has given up on."""

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        """Store the failed delivery for later inspection or replay.

        Implementations must not raise for an ordinary storage failure. A sink that throws
        would fail the dispatcher's *error* path, which is precisely where the code has least
        margin: the event would go back to pending and be retried forever on the strength of
        a fault in the machinery meant to end the retrying.
        """
        ...


class LoggingDeadLetterSink:
    """The default sink: log the failure, retain it in memory for the current process.

    The in-memory list is bounded. An unbounded one would turn a producer emitting a bad
    payload in a loop -- the exact scenario this class exists for -- into a memory leak in
    the consumer, so a burst of failures degrades to keeping the most recent rather than
    keeping everything until the pod dies.
    """

    def __init__(self, *, capacity: int = 100) -> None:
        self._capacity = max(1, capacity)
        self._parked: list[DeadLetter] = []

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        """Record the failure at ``error`` and retain it, evicting the oldest if full."""
        logger.error(
            "notification.event.dead_lettered delivery_id=%s attempt=%d reason=%s payload=%s",
            delivery.delivery_id,
            delivery.attempt,
            reason,
            delivery.payload,
        )
        self._parked.append(DeadLetter(delivery=delivery, reason=reason))
        if len(self._parked) > self._capacity:
            del self._parked[0]

    @property
    def parked(self) -> Sequence[DeadLetter]:
        """Everything parked in this process, oldest first."""
        return tuple(self._parked)
