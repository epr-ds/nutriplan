"""Counters for what the consumer did, so NTF-706 has something to export (NTF-204, AC3).

Deliberately not Prometheus. NTF-706 owns the export format, the dashboards and the alerts;
what it needs from this story is that the numbers *exist* and are correct, and picking a client
library here would make that choice on its behalf -- in the module least able to change it
later, because every call site would already depend on the type.

So this is a dict of integers behind a small interface, and the whole of NTF-706's job on this
side is one adapter that reads :meth:`EventMetrics.snapshot`.

**Counted, not derived.** :class:`~app.events.dispatcher.BatchResult` already reports what one
batch did, and it is not a metric: it is returned to the caller and discarded. A restart-safe
count is not wanted either -- these are process-lifetime counters, which is exactly what a
Prometheus counter is, and what makes ``rate()`` over them meaningful across a deploy.

**Depth is read, never counted.** The one number NTF-706 alerts on -- how many events are
sitting in the dead-letter queue -- is deliberately absent from this module. A counter of
parks minus removes would drift from reality the first time an entry aged out under its TTL or
a second replica parked something, and a dead-letter alert that has quietly drifted is worse
than no alert. It is a live read of
:meth:`~app.events.dead_letter.DeadLetterQueue.depth` instead.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from enum import StrEnum

UNTYPED = "-"
"""Stands in for the event type when the payload was too broken to name one.

A real label rather than an omission: an operator watching dead letters by type needs to see
that a hundred of them could not be parsed at all, and a series that simply is not there
reads as "nothing is failing".
"""


class Outcome(StrEnum):
    """Every way a delivery can be settled. One series per value."""

    HANDLED = "handled"
    """A handler ran and returned. The success case."""

    DROPPED = "dropped"
    """Acked without acting -- an unknown type, or a known one with no handler registered."""

    RETRIED = "retried"
    """Left pending after a transient failure, to be reclaimed once its backoff elapses."""

    DEFERRED = "deferred"
    """Seen in the pending list but not yet due under the backoff schedule.

    The series that distinguishes "backoff is working" from "the consumer has stopped": a
    queue that is not draining looks identical from the outside either way, and this is the
    number that tells them apart.
    """

    DEAD_LETTERED = "dead_lettered"
    """Parked permanently -- the budget ran out, or the failure could never be retried away."""

    REPLAYED = "replayed"
    """A parked event was re-run successfully and removed from the queue."""

    REPLAY_FAILED = "replay_failed"
    """A parked event was re-run and failed again, so it stays parked."""


class EventMetrics:
    """Process-lifetime counts of delivery outcomes, in total and by event type.

    Thread-safe because the worker and any future replay thread both write, and a lost
    increment is the kind of defect that is only ever noticed as a graph that does not add up.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals: dict[Outcome, int] = dict.fromkeys(Outcome, 0)
        self._by_type: dict[Outcome, dict[str, int]] = {outcome: {} for outcome in Outcome}

    def increment(self, outcome: Outcome, *, event_type: str | None = None, count: int = 1) -> None:
        """Add ``count`` to one outcome, and to its per-type breakdown."""
        if count <= 0:
            return
        label = event_type or UNTYPED
        with self._lock:
            self._totals[outcome] += count
            by_type = self._by_type[outcome]
            by_type[label] = by_type.get(label, 0) + count

    def total(self, outcome: Outcome) -> int:
        """How many deliveries have been settled this way since the process started."""
        with self._lock:
            return self._totals[outcome]

    def by_type(self, outcome: Outcome) -> Mapping[str, int]:
        """The per-event-type breakdown of one outcome."""
        with self._lock:
            return dict(self._by_type[outcome])

    def snapshot(self) -> Mapping[str, Mapping[str, int]]:
        """Every counter at once, for NTF-706's exporter and for the DLQ CLI's summary.

        One consistent read rather than a series of per-outcome calls: a snapshot taken while
        a batch is being settled would otherwise be able to show a delivery counted as neither
        handled nor retried, which is the sort of arithmetic that sends someone hunting a bug
        in the consumer instead of in the dashboard.
        """
        with self._lock:
            return {
                "totals": {outcome.value: count for outcome, count in self._totals.items()},
                **{
                    outcome.value: dict(counts)
                    for outcome, counts in self._by_type.items()
                    if counts
                },
            }
