"""The dead-letter queue: what happens to an event nothing can do anything with (NTF-204).

NTF-201 left a deliberate stub here -- a sink that logged the failure and kept it in a list
that died with the process. That was honest for a framework story with no handlers, and it
stops being honest the moment NTF-202 starts parking real order events. A queue nothing can
read is not a queue; it is a slower way of dropping messages.

So this module widens the seam from *park* to a queue an operator can act on:

===============  =============================================================
``park``         accept a permanently-failed delivery (NTF-201's contract)
``list``/``get`` see what is in there, newest first
``depth``        how many, for the metric NTF-706 alerts on
``remove``       drop one entry, after a replay has succeeded
``purge``        empty it, once the failures have been understood
===============  =============================================================

**Why the entries carry a parsed summary.** :class:`DeadLetter` keeps the raw payload verbatim
-- that is the evidence, and a partially-parsed rendering of a broken message discards the very
thing that made it broken. But it *also* stores the event type and id when they could be read,
because the alternative is that listing a hundred parked entries means re-parsing a hundred
payloads in the CLI, and half of them are parked precisely because they cannot be parsed. A
summary that is allowed to be ``None`` costs one nullable field and makes the queue legible.

**Parking must not raise.** Inherited from NTF-201 and worth restating, because the wider port
gives it more ways to go wrong: :meth:`DeadLetterQueue.park` is called on the dispatcher's
error path, where the code has least margin. A sink that threw would fail the handling of a
failure -- the delivery would go back to pending and be retried forever on the strength of a
fault in the machinery meant to end the retrying.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.events.consumer import DeliveredEvent

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY = 500
"""How many parked entries are kept before the oldest are evicted.

Bounded because the scenario this queue exists for -- a producer emitting a bad payload in a
loop -- is also the scenario that fills it fastest, and an unbounded dead-letter queue turns
one broken producer into an outage of the consumer that was trying to tell you about it.
"""


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """A permanently-failed delivery, kept with enough context to act on later."""

    delivery: DeliveredEvent
    reason: str
    """Why it was parked, in words an operator can act on -- not an exception repr."""

    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    event_type: str | None = None
    """The envelope's type, when the payload could be read far enough to find it.

    ``None`` means the payload was unparseable, which is itself the most useful thing a
    listing can say about an entry.
    """

    event_id: str | None = None
    """The producer's event id -- the one NTF-103 dedupes on, so a replay of an event that
    *was* handled before failing is suppressed rather than duplicated."""

    @property
    def delivery_id(self) -> str:
        """The broker id of the parked delivery."""
        return self.delivery.delivery_id

    @property
    def attempt(self) -> int:
        """Which delivery attempt was the last one."""
        return self.delivery.attempt

    @property
    def payload(self) -> str:
        """The bytes as published, verbatim -- what makes the failure reproducible."""
        return self.delivery.payload

    @classmethod
    def of(cls, delivery: DeliveredEvent, *, reason: str) -> DeadLetter:
        """Build an entry, reading the type and id off the payload if they are there."""
        event_type, event_id = summarize(delivery.payload)
        return cls(
            delivery=delivery,
            reason=reason,
            event_type=event_type,
            event_id=event_id,
        )


@runtime_checkable
class DeadLetterQueue(Protocol):
    """Where events the consumer has given up on wait for an operator."""

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        """Store the failed delivery for later inspection or replay.

        Implementations must not raise for an ordinary storage failure -- see the module
        docstring for why the error path is the wrong place to introduce a new one.
        """
        ...

    def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[DeadLetter]:
        """Return parked entries, most recently failed first."""
        ...

    def get(self, delivery_id: str) -> DeadLetter | None:
        """Return one parked entry, or ``None`` if it is not there (or has aged out)."""
        ...

    def depth(self) -> int:
        """How many entries are parked. The number NTF-706 alerts on when it grows."""
        ...

    def remove(self, delivery_id: str) -> bool:
        """Drop one entry, returning whether it was there. Called after a successful replay."""
        ...

    def purge(self) -> int:
        """Empty the queue, returning how many entries were discarded."""
        ...


class InMemoryDeadLetterQueue:
    """The dev/CI queue: log every failure, retain a bounded window of it in this process.

    Logging is not durability and is not pretending to be. What it does buy is that on the day
    a malformed event arrives in an environment with no Redis, the payload is in the log where
    someone can find it, rather than gone.

    Thread-safe for the same reason the in-process consumer is: the worker parks on its own
    thread while a test inspects the queue from another, and a race here would surface as a
    flaky test blamed on the framework.
    """

    def __init__(self, *, capacity: int = DEFAULT_CAPACITY) -> None:
        self._capacity = max(1, capacity)
        self._lock = threading.RLock()
        self._entries: dict[str, DeadLetter] = {}

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        """Record the failure at ``error`` and retain it, evicting the oldest if full."""
        logger.error(
            "notification.event.dead_lettered delivery_id=%s attempt=%d reason=%s payload=%s",
            delivery.delivery_id,
            delivery.attempt,
            reason,
            delivery.payload,
        )
        with self._lock:
            # Re-parking a delivery id replaces the entry rather than adding a second: the
            # queue is keyed by delivery, and two rows for one message would double-count the
            # depth NTF-706 alerts on.
            self._entries.pop(delivery.delivery_id, None)
            self._entries[delivery.delivery_id] = DeadLetter.of(delivery, reason=reason)
            while len(self._entries) > self._capacity:
                # dicts preserve insertion order, so the first key is the oldest arrival.
                del self._entries[next(iter(self._entries))]

    def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[DeadLetter]:
        with self._lock:
            # Sorted on ``(failed_at, delivery_id)`` descending to replicate the Redis
            # adapter exactly: a sorted set with equal scores orders by member, and two
            # entries parked in the same microsecond are common enough (a producer looping
            # on a bad payload is the scenario this queue exists for) that leaving the
            # tie-break to a stable sort would have the two adapters disagree about which
            # entry is newest -- an ordering bug that would reproduce in CI only by luck.
            newest_first = sorted(
                self._entries.values(),
                key=lambda entry: (entry.failed_at, entry.delivery_id),
                reverse=True,
            )
        start = max(0, offset)
        return tuple(newest_first[start : start + max(0, limit)])

    def get(self, delivery_id: str) -> DeadLetter | None:
        with self._lock:
            return self._entries.get(delivery_id)

    def depth(self) -> int:
        with self._lock:
            return len(self._entries)

    def remove(self, delivery_id: str) -> bool:
        with self._lock:
            return self._entries.pop(delivery_id, None) is not None

    def purge(self) -> int:
        with self._lock:
            discarded = len(self._entries)
            self._entries.clear()
            return discarded

    @property
    def parked(self) -> Sequence[DeadLetter]:
        """Everything parked in this process, oldest first -- NTF-201's accessor, kept."""
        with self._lock:
            return tuple(self._entries.values())


def summarize(payload: str) -> tuple[str | None, str | None]:
    """Read the type and event id off a payload, tolerating one that cannot be read at all.

    Deliberately not :func:`~app.events.envelope.parse_envelope`: that validates, and this runs
    over payloads whose defining property is that validation failed. All that is wanted here is
    whatever the entry can be labelled with in a listing.
    """
    try:
        parsed: Any = json.loads(payload)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(parsed, Mapping):
        return None, None
    return _text(parsed.get("type")), _text(parsed.get("id"))


def _text(value: Any) -> str | None:
    """Return a non-blank string, or ``None`` for anything else."""
    return value.strip() or None if isinstance(value, str) else None
