"""Getting an event out of the dead-letter queue and back through the handler (NTF-204, AC2).

A dead-letter queue is only half a feature. Parking an event stops it blocking the stream, but
the event still has not been acted on -- a user is still missing the notification that was
supposed to tell them their order shipped. Replay is the other half: once the cause is fixed
and deployed, the parked events are run again, and the ones that now work leave the queue.

**Replay does not go back through the bus.** The obvious implementation re-publishes the parked
payload to the stream, and this service must not: it *consumes* commerce's order stream and has
no business writing to it. A notification service that appended to a commerce topic would be
inventing order events, and every other consumer of that stream -- present and future -- would
see them. So a replay runs the same parse, registry and handler chain in-process, against the
stored bytes, with nothing acked because there is nothing left pending to ack.

**A failed replay changes nothing.** The entry stays in the queue with its original reason
intact, so replaying is safe to run repeatedly and against everything -- which matters, because
the realistic operational move after a fix ships is "replay all of it and see what drains", not
"work out which seventeen of these ninety entries the fix addressed". Re-parking on failure
would overwrite the original failure reason with an identical one and reset the entry's
position in the queue, making an entry that has failed replay six times look freshly broken.

**Dedupe does the work replay must not do.** Some parked events *were* partially processed
before failing. Replaying those must not hand the user a second copy, and nothing in this module
prevents it -- NTF-103 does, because the dedupe key is derived from the envelope's event id,
which the stored payload still carries. That is the whole reason the key is keyed on the
producer's id rather than the broker's delivery id: a replay is a new delivery of the same
event, and only one of those two identifiers stays put.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.events.dead_letter import DeadLetterQueue
from app.events.dispatcher import EventDispatcher, NoHandlerRegistered
from app.events.errors import EventError
from app.events.metrics import EventMetrics, Outcome

logger = logging.getLogger(__name__)


class ReplayStatus(StrEnum):
    """How one attempt to replay a parked event ended."""

    REPLAYED = "replayed"
    """It ran, and the entry has been removed from the queue."""

    STILL_FAILING = "still_failing"
    """It failed the same permanent way. The entry stays parked, reason untouched."""

    UNAVAILABLE = "unavailable"
    """It failed transiently -- a dependency is down. Worth trying again later, unchanged."""

    NOT_FOUND = "not_found"
    """No such entry: already replayed by another operator, or aged out under its TTL."""


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    """What happened to one entry, in a form the CLI can print and a test can assert on."""

    delivery_id: str
    status: ReplayStatus
    detail: str = ""
    event_type: str | None = None

    @property
    def succeeded(self) -> bool:
        """True only when the event was handled and the entry is gone from the queue."""
        return self.status is ReplayStatus.REPLAYED


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """The result of draining a batch of the queue."""

    outcomes: Sequence[ReplayOutcome] = ()

    @property
    def replayed(self) -> int:
        """How many entries ran successfully and were removed."""
        return sum(1 for outcome in self.outcomes if outcome.succeeded)

    @property
    def remaining(self) -> int:
        """How many were tried and are still parked."""
        return len(self.outcomes) - self.replayed

    def of_status(self, status: ReplayStatus) -> Sequence[ReplayOutcome]:
        """Every outcome with a given status, for a caller that wants to report by kind."""
        return tuple(outcome for outcome in self.outcomes if outcome.status is status)


class DeadLetterReplayer:
    """Re-runs parked events through the dispatcher and drains the ones that now work."""

    def __init__(
        self,
        queue: DeadLetterQueue,
        dispatcher: EventDispatcher,
        *,
        metrics: EventMetrics | None = None,
    ) -> None:
        self._queue = queue
        self._dispatcher = dispatcher
        # Defaults to the dispatcher's own counters so a replay shows up on the same series
        # NTF-706 graphs. Injectable because a caller may want the replay run's numbers in
        # isolation.
        self._metrics = metrics or dispatcher.metrics

    def replay(self, delivery_id: str) -> ReplayOutcome:
        """Re-run one parked event, removing it from the queue only if it succeeded."""
        entry = self._queue.get(delivery_id)
        if entry is None:
            return ReplayOutcome(delivery_id, ReplayStatus.NOT_FOUND, "no such parked entry")

        try:
            event_type = self._dispatcher.replay(entry.payload)
        except NoHandlerRegistered as exc:
            # Distinguished from an ordinary permanent failure only in the message: an
            # operator seeing this needs to know the event is not broken, the wiring is.
            return self._failed(entry.delivery_id, entry.event_type, str(exc))
        except EventError as exc:
            return self._failed(entry.delivery_id, entry.event_type, str(exc))
        except Exception as exc:
            logger.warning(
                "notification.event.replay_unavailable delivery_id=%s error=%s",
                entry.delivery_id,
                exc,
            )
            self._metrics.increment(Outcome.REPLAY_FAILED, event_type=entry.event_type)
            return ReplayOutcome(
                entry.delivery_id, ReplayStatus.UNAVAILABLE, str(exc), entry.event_type
            )

        # Removal follows the handler, never precedes it. A crash between the two leaves the
        # entry parked and replayable a second time, which dedupe absorbs; removing first
        # would delete the only copy of an event that then failed to run.
        self._queue.remove(entry.delivery_id)
        self._metrics.increment(Outcome.REPLAYED, event_type=event_type)
        logger.info(
            "notification.event.replayed delivery_id=%s type=%s", entry.delivery_id, event_type
        )
        return ReplayOutcome(entry.delivery_id, ReplayStatus.REPLAYED, event_type=event_type)

    def replay_all(self, *, limit: int = 100) -> ReplayReport:
        """Replay up to ``limit`` parked events, oldest first.

        Oldest first because a queue is drained in the order it filled: the events that have
        been undelivered longest are the ones a user is most obviously missing. It also means
        a run that hits a limit makes monotonic progress instead of repeatedly re-trying the
        newest arrivals while a backlog ages behind them.

        The listing is taken once, up front. Replaying mutates the queue -- successful entries
        are removed -- so iterating a live view would renumber the offsets underneath the loop
        and skip entries.
        """
        entries = list(self._queue.list(limit=max(0, limit)))
        entries.reverse()
        return ReplayReport(tuple(self.replay(entry.delivery_id) for entry in entries))

    def _failed(self, delivery_id: str, event_type: str | None, detail: str) -> ReplayOutcome:
        """Record a permanent replay failure, leaving the entry exactly as it was."""
        self._metrics.increment(Outcome.REPLAY_FAILED, event_type=event_type)
        logger.info(
            "notification.event.replay_failed delivery_id=%s reason=%s", delivery_id, detail
        )
        return ReplayOutcome(delivery_id, ReplayStatus.STILL_FAILING, detail, event_type)
