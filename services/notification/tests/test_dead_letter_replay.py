"""Re-running parked events once the reason they failed is fixed (NTF-204, AC2).

Replay is the half of the dead-letter story that makes parking worth doing: without it, a
DLQ is a graveyard with an audit trail. The behaviour that matters is what happens when a
replay *doesn't* work, because that is the common case -- an operator replays after a deploy
and some entries are fixed while others are not, and the queue has to still be trustworthy
afterwards.
"""

from __future__ import annotations

import json

import pytest

from app.application.dead_letter_replay import (
    DeadLetterReplayer,
    ReplayStatus,
)
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import InMemoryDeadLetterQueue
from app.events.dispatcher import EventDispatcher
from app.events.envelope import EventEnvelope
from app.events.errors import EventError
from app.events.memory import InMemoryEventConsumer
from app.events.metrics import EventMetrics, Outcome
from app.events.registry import ORDER_CONFIRMED, default_registry
from tests.test_event_envelope import COMMERCE_ORDER_CONFIRMED


class RecordingHandler:
    """Accepts everything and remembers what it saw."""

    def __init__(self) -> None:
        self.seen: list[EventEnvelope] = []

    def handle(self, event: EventEnvelope) -> None:
        self.seen.append(event)


class FailingHandler:
    """Raises a chosen exception on every event, counting the attempts."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def handle(self, event: EventEnvelope) -> None:
        self.calls += 1
        raise self._error


class Harness:
    """A replayer over a queue and dispatcher that share their collaborators."""

    def __init__(self, handler: object | None = None) -> None:
        self.handler = handler if handler is not None else RecordingHandler()
        self.queue = InMemoryDeadLetterQueue()
        self.consumer = InMemoryEventConsumer()
        self.dispatcher = EventDispatcher(
            self.consumer,
            registry=default_registry(),
            dead_letters=self.queue,
            handlers={ORDER_CONFIRMED: self.handler},
        )
        self.replayer = DeadLetterReplayer(self.queue, self.dispatcher)

    def park(
        self, delivery_id: str = "d-1", *, payload: str | None = None, reason: str = "nope"
    ) -> str:
        """Put one entry in the queue, as the dispatcher's error path would."""
        body = payload if payload is not None else json.dumps(COMMERCE_ORDER_CONFIRMED)
        self.queue.park(
            DeliveredEvent(delivery_id=delivery_id, payload=body, attempt=5), reason=reason
        )
        return delivery_id

    @property
    def parked_ids(self) -> list[str]:
        return [entry.delivery_id for entry in self.queue.list(limit=100)]


class TestASuccessfulReplay:
    def test_the_handler_runs_on_the_stored_payload(self) -> None:
        harness = Harness()
        harness.park()

        harness.replayer.replay("d-1")

        assert len(harness.handler.seen) == 1  # type: ignore[attr-defined]

    def test_the_outcome_says_it_was_replayed(self) -> None:
        harness = Harness()
        harness.park()

        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.REPLAYED
        assert outcome.succeeded is True
        assert outcome.event_type == ORDER_CONFIRMED

    def test_the_entry_leaves_the_queue(self) -> None:
        harness = Harness()
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.queue.depth() == 0

    def test_it_is_counted(self) -> None:
        harness = Harness()
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.dispatcher.metrics.total(Outcome.REPLAYED) == 1

    def test_nothing_is_published_back_to_the_stream(self) -> None:
        """Replay re-runs the handler in-process; it must not write to commerce's stream.

        Notification is a consumer of that stream and has no business appending to it --
        a replay that re-published would fan out to every other consumer group as well,
        turning one service's operational retry into everybody's duplicate event.
        """
        harness = Harness()
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.consumer.pending_count == 0
        assert harness.consumer.poll(count=10, block_ms=0) == ()


class TestAReplayThatStillFails:
    def test_a_permanent_failure_leaves_the_entry_parked(self) -> None:
        """The entry is the only copy -- losing it because the fix isn't deployed yet is
        exactly the outcome the queue exists to prevent."""
        harness = Harness(FailingHandler(EventError("still missing userId")))
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.queue.depth() == 1

    def test_the_outcome_says_it_is_still_failing(self) -> None:
        harness = Harness(FailingHandler(EventError("still missing userId")))
        harness.park()

        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.STILL_FAILING
        assert outcome.succeeded is False

    def test_the_reason_reaches_the_operator(self) -> None:
        harness = Harness(FailingHandler(EventError("still missing userId")))
        harness.park()

        outcome = harness.replayer.replay("d-1")

        assert "still missing userId" in outcome.detail

    def test_the_original_park_reason_is_not_overwritten(self) -> None:
        """A failed replay must not re-park.

        Re-parking would reset ``failed_at`` and replace the reason, so an entry that has
        failed six times would look like it arrived just now -- and a queue sorted newest
        first would shuffle the oldest problems to the top every time someone ran a replay.
        """
        harness = Harness(FailingHandler(EventError("still broken")))
        harness.park(reason="the original diagnosis")
        before = harness.queue.get("d-1")

        harness.replayer.replay("d-1")

        after = harness.queue.get("d-1")
        assert after is not None and before is not None
        assert after.reason == "the original diagnosis"
        assert after.failed_at == before.failed_at
        assert after.attempt == before.attempt

    def test_a_missing_handler_is_reported_as_a_wiring_problem(self) -> None:
        """The event is fine and the service is not -- an operator needs to be told which."""
        harness = Harness()
        harness.dispatcher._handlers.clear()  # noqa: SLF001 - simulating a deploy that lost it
        harness.park()

        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.STILL_FAILING
        assert "no handler" in outcome.detail

    def test_a_still_failing_replay_is_counted(self) -> None:
        harness = Harness(FailingHandler(EventError("still broken")))
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.dispatcher.metrics.total(Outcome.REPLAY_FAILED) == 1

    def test_it_can_be_replayed_again_once_the_fix_lands(self) -> None:
        """The whole point of leaving it parked."""
        handler = FailingHandler(EventError("not yet"))
        harness = Harness(handler)
        harness.park()
        harness.replayer.replay("d-1")

        harness.dispatcher._handlers[ORDER_CONFIRMED] = RecordingHandler()  # noqa: SLF001
        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.REPLAYED
        assert harness.queue.depth() == 0


class TestATransientFailureIsNotMistakenForAPermanentOne:
    def test_an_unexpected_exception_is_reported_as_unavailable(self) -> None:
        """Replaying against a dependency that is down must not read as "still broken".

        The two need different actions -- wait and retry versus fix and deploy -- and
        reporting the first as the second sends an operator chasing a bug in the payload.
        """
        harness = Harness(FailingHandler(ConnectionError("redis is down")))
        harness.park()

        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.UNAVAILABLE
        assert outcome.succeeded is False

    def test_the_entry_stays_parked(self) -> None:
        harness = Harness(FailingHandler(ConnectionError("redis is down")))
        harness.park()

        harness.replayer.replay("d-1")

        assert harness.queue.depth() == 1

    def test_the_error_does_not_escape(self) -> None:
        """One unreachable dependency must not abandon a ``replay --all`` mid-drain."""
        harness = Harness(FailingHandler(ConnectionError("redis is down")))
        harness.park()

        harness.replayer.replay("d-1")  # must not raise


class TestAnEntryThatIsNotThere:
    def test_it_is_reported_as_not_found(self) -> None:
        outcome = Harness().replayer.replay("never-parked")

        assert outcome.status is ReplayStatus.NOT_FOUND
        assert outcome.succeeded is False

    def test_the_handler_is_not_run(self) -> None:
        harness = Harness()

        harness.replayer.replay("never-parked")

        assert harness.handler.seen == []  # type: ignore[attr-defined]


class TestDrainingTheWholeQueue:
    def test_every_entry_is_replayed(self) -> None:
        harness = Harness()
        for index in range(3):
            harness.park(f"d-{index}")

        report = harness.replayer.replay_all()

        assert len(report.outcomes) == 3
        assert harness.queue.depth() == 0

    def test_it_drains_oldest_first(self) -> None:
        """A queue is drained in the order it filled: the longest-undelivered events are
        the ones a user is most obviously missing, and a run that hits its limit then makes
        monotonic progress instead of re-trying the newest arrivals forever."""
        harness = Harness()
        for index in range(3):
            harness.park(f"d-{index}")

        report = harness.replayer.replay_all()

        assert [outcome.delivery_id for outcome in report.outcomes] == ["d-0", "d-1", "d-2"]

    def test_a_limit_caps_the_run(self) -> None:
        harness = Harness()
        for index in range(5):
            harness.park(f"d-{index}")

        report = harness.replayer.replay_all(limit=2)

        assert len(report.outcomes) == 2
        assert harness.queue.depth() == 3

    def test_the_failures_stay_and_the_successes_go(self) -> None:
        """The mixed run is the realistic one, and the reason removal is per-entry."""

        class FussyHandler:
            def handle(self, event: EventEnvelope) -> None:
                if event.data.get("orderId") == "bad":
                    raise EventError("this one is still broken")

        harness = Harness(FussyHandler())
        harness.park("d-good")
        harness.park(
            "d-bad",
            payload=json.dumps({**COMMERCE_ORDER_CONFIRMED, "data": {"orderId": "bad"}}),
        )

        report = harness.replayer.replay_all()

        assert harness.parked_ids == ["d-bad"]
        assert report.replayed == 1
        assert report.remaining == 1
        still_failing = report.of_status(ReplayStatus.STILL_FAILING)
        assert [outcome.delivery_id for outcome in still_failing] == ["d-bad"]

    def test_the_listing_is_taken_once(self) -> None:
        """Replaying mutates the queue, so iterating a live view would renumber the offsets
        underneath the loop and skip every second entry."""
        harness = Harness()
        for index in range(4):
            harness.park(f"d-{index}")

        report = harness.replayer.replay_all()

        assert len(report.outcomes) == 4
        assert harness.queue.depth() == 0

    def test_an_empty_queue_is_an_empty_report(self) -> None:
        report = Harness().replayer.replay_all()

        assert report.outcomes == ()
        assert report.replayed == 0

    def test_outcomes_can_be_filtered_by_status(self) -> None:
        harness = Harness(FailingHandler(EventError("broken")))
        harness.park("d-0")
        harness.park("d-1")

        report = harness.replayer.replay_all()

        assert len(report.of_status(ReplayStatus.STILL_FAILING)) == 2
        assert report.of_status(ReplayStatus.REPLAYED) == ()


class TestReplayIsSafeToRunTwice:
    def test_replaying_an_already_replayed_entry_is_not_found(self) -> None:
        """So a runbook step that is run twice reports nothing to do rather than doing it."""
        harness = Harness()
        harness.park()
        harness.replayer.replay("d-1")

        outcome = harness.replayer.replay("d-1")

        assert outcome.status is ReplayStatus.NOT_FOUND

    def test_replay_all_twice_over_a_failing_queue_does_not_multiply_entries(self) -> None:
        harness = Harness(FailingHandler(EventError("broken")))
        harness.park("d-0")

        harness.replayer.replay_all()
        harness.replayer.replay_all()

        assert harness.queue.depth() == 1


class TestMetrics:
    def test_it_shares_the_dispatchers_counters_by_default(self) -> None:
        """So a replay shows up on the same series NTF-706 graphs the live path on."""
        harness = Harness()

        assert DeadLetterReplayer(harness.queue, harness.dispatcher)._metrics is (  # noqa: SLF001
            harness.dispatcher.metrics
        )

    def test_a_caller_can_isolate_a_runs_numbers(self) -> None:
        harness = Harness()
        harness.park()
        own = EventMetrics()

        DeadLetterReplayer(harness.queue, harness.dispatcher, metrics=own).replay("d-1")

        assert own.total(Outcome.REPLAYED) == 1
        assert harness.dispatcher.metrics.total(Outcome.REPLAYED) == 0


class TestTheOutcome:
    @pytest.mark.parametrize(
        ("status", "succeeded"),
        [
            (ReplayStatus.REPLAYED, True),
            (ReplayStatus.STILL_FAILING, False),
            (ReplayStatus.UNAVAILABLE, False),
            (ReplayStatus.NOT_FOUND, False),
        ],
    )
    def test_only_a_replayed_entry_counts_as_success(
        self, status: ReplayStatus, succeeded: bool
    ) -> None:
        from app.application.dead_letter_replay import ReplayOutcome

        assert ReplayOutcome("d-1", status).succeeded is succeeded
