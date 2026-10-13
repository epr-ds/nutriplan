"""An in-process consumer for dev, CI and tests (NTF-201).

The counterpart to commerce's :class:`~app.events.memory.InMemoryEventPublisher`: when no
bus URL is configured, events never leave the process, and this stands in for the broker.

It would be much easier to make this a queue that hands out messages and forgets them. It is
deliberately not, because the whole point of the port is that the two adapters are
interchangeable, and a stand-in that never redelivers is not a stand-in for an at-least-once
bus -- it is a more forgiving world. Every ordering bug the framework exists to prevent would
pass in dev and CI and appear only against real Redis.

So this class reproduces the parts of a Redis consumer group that the semantics depend on:

* a message stays **pending** until it is acked;
* the pending entry remembers a **delivery count** and the time it was last handed out;
* :meth:`reclaim` returns pending messages whose backoff has elapsed, incrementing that
  count -- which is what a crashed consumer's messages do under ``XCLAIM``;
* the same :class:`~app.events.backoff.RetrySchedule` decides due-ness, jitter included, so
  NTF-204's backoff is exercised in CI rather than only in production;
* the group has an **offset**, and one created against a stream that already has entries
  starts at the end of it, exactly as ``XGROUP CREATE ... $`` does.

What it does not reproduce is durability or sharing between processes -- which is precisely
the property ``/health/ready`` reports as a warning outside production and a failure inside
it (NTF-101), so the honest limitation is already surfaced where it matters.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.events.backoff import RetrySchedule
from app.events.consumer import DeliveredEvent, ReclaimResult

MONOTONIC_START = 1
"""Entry ids count from 1; Redis uses ``<ms>-<seq>``, but only ordering is relied on."""


@dataclass
class _Pending:
    """One delivered-but-unacked entry, mirroring a row of Redis's pending-entries list."""

    payload: str
    delivered_count: int
    last_delivered_at: float


class InMemoryEventConsumer:
    """A single-process stand-in for a Redis Streams consumer group.

    Thread-safe because the worker polls on one thread while tests publish from another, and
    a race here would surface as a flaky test blamed on the framework rather than the fixture.
    """

    def __init__(self, *, clock: Any = None) -> None:
        import time

        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._entries: list[tuple[str, str]] = []
        self._pending: dict[str, _Pending] = {}
        self._ids = itertools.count(MONOTONIC_START)
        self._offset = 0
        self._group_created = False

    # -- producer side, for tests and the dev path -------------------------------------

    def publish(self, envelope: Mapping[str, Any] | str) -> str:
        """Append an envelope to the stream, returning its entry id.

        Accepts a mapping for convenience and serializes it the way the real publisher does,
        so a test writing a dict still exercises the JSON round-trip that production runs.
        """
        payload = envelope if isinstance(envelope, str) else json.dumps(dict(envelope))
        with self._lock:
            entry_id = str(next(self._ids))
            self._entries.append((entry_id, payload))
            return entry_id

    @property
    def pending_count(self) -> int:
        """How many delivered messages are still unacked."""
        with self._lock:
            return len(self._pending)

    # -- consumer port ------------------------------------------------------------------

    def ensure_group(self) -> None:
        """Create the group at the *end* of the stream, as ``XGROUP CREATE ... $`` does."""
        with self._lock:
            if self._group_created:
                return
            self._offset = len(self._entries)
            self._group_created = True

    def poll(self, *, count: int, block_ms: int = 0) -> Sequence[DeliveredEvent]:
        """Hand out up to ``count`` never-before-delivered entries.

        ``block_ms`` is accepted and ignored: there is no other thread to wait for that could
        not have published before the call. Blocking here would only slow the suite down.
        """
        with self._lock:
            self.ensure_group()
            batch = self._entries[self._offset : self._offset + max(0, count)]
            self._offset += len(batch)
            now = self._clock()
            delivered = []
            for entry_id, payload in batch:
                self._pending[entry_id] = _Pending(payload, 1, now)
                delivered.append(DeliveredEvent(entry_id, payload, attempt=1))
            return tuple(delivered)

    def reclaim(self, *, schedule: RetrySchedule, count: int) -> ReclaimResult:
        """Re-serve pending entries whose backoff has elapsed, bumping the attempt.

        Applies the same schedule the Redis adapter does, including the per-entry jitter
        derived from the entry id. A stand-in that retried everything on a flat threshold
        would make every backoff test pass in CI and prove nothing about production.
        """
        with self._lock:
            now = self._clock()
            claimed = []
            deferred = 0
            for entry_id in sorted(self._pending, key=int):
                if len(claimed) >= max(0, count):
                    break
                entry = self._pending[entry_id]
                idle_ms = int((now - entry.last_delivered_at) * 1000)
                if not schedule.is_due(
                    attempt=entry.delivered_count, idle_ms=idle_ms, delivery_id=entry_id
                ):
                    deferred += 1
                    continue
                entry.delivered_count += 1
                entry.last_delivered_at = now
                claimed.append(
                    DeliveredEvent(entry_id, entry.payload, attempt=entry.delivered_count)
                )
            return ReclaimResult(deliveries=tuple(claimed), deferred=deferred)

    def ack(self, delivery_id: str) -> None:
        """Settle a message. Acking an unknown or already-acked id is a no-op, as ``XACK`` is."""
        with self._lock:
            self._pending.pop(delivery_id, None)
