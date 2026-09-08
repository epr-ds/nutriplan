"""The settle-or-retry rules applied to one delivery (NTF-201, AC1).

Each test here corresponds to a row of the table in :mod:`app.events.dispatcher`. The
assertion that recurs is not "did the handler run" but **"is the message still pending"**,
because that is the part that decides whether a user eventually gets their notification or
never does.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from app.events.backoff import RetrySchedule
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import DeadLetterQueue, InMemoryDeadLetterQueue
from app.events.dispatcher import BatchResult, EventDispatcher
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent, UnsupportedEvent
from app.events.memory import InMemoryEventConsumer
from app.events.registry import ORDER_CONFIRMED, default_registry
from tests.test_event_envelope import COMMERCE_ORDER_CONFIRMED, envelope

NO_BACKOFF = RetrySchedule(base_ms=0, jitter=0.0)
"""Everything is due the moment it is pending -- NTF-201's behaviour, for tests about
the settle rules rather than about the schedule itself (which test_event_backoff owns)."""


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


class ExplodingSink:
    """A dead-letter sink that breaks its own contract, to prove the ordering holds."""

    def park(self, delivery: DeliveredEvent, *, reason: str) -> None:
        raise RuntimeError("the dead-letter store is down")


class Harness:
    """A dispatcher over an in-process consumer, with the collaborators exposed."""

    def __init__(
        self,
        *,
        handlers: Mapping[str, Any] | None = None,
        max_attempts: int = 5,
        dead_letters: DeadLetterQueue | None = None,
    ) -> None:
        self.consumer = InMemoryEventConsumer()
        self.consumer.ensure_group()
        self.sink = dead_letters or InMemoryDeadLetterQueue()
        self.dispatcher = EventDispatcher(
            self.consumer,
            registry=default_registry(),
            dead_letters=self.sink,
            handlers=handlers,
            max_attempts=max_attempts,
        )

    def publish(self, event: Mapping[str, Any] | str) -> None:
        self.consumer.publish(event)

    def run(self) -> BatchResult:
        """Poll one batch and settle it."""
        return self.dispatcher.poll_once(count=10, block_ms=0)

    @property
    def pending(self) -> int:
        """Deliveries still unsettled -- the number that decides redelivery."""
        return self.consumer.pending_count

    @property
    def parked_reasons(self) -> list[str]:
        return [entry.reason for entry in self.sink.parked]  # type: ignore[attr-defined]


class TestASuccessfulHandlerSettlesTheDelivery:
    def test_the_handler_receives_the_parsed_envelope(self) -> None:
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert len(handler.seen) == 1
        assert handler.seen[0].type == ORDER_CONFIRMED
        assert handler.seen[0].data["orderId"] == COMMERCE_ORDER_CONFIRMED["data"]["orderId"]  # type: ignore[index]

    def test_the_delivery_is_acked(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        result = harness.run()

        assert result == BatchResult(handled=1)
        assert harness.pending == 0

    def test_nothing_is_parked(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert harness.parked_reasons == []


class TestATransientFailureIsRedelivered:
    """The asymmetry that matters: an unclassified failure must not lose an event."""

    def test_the_delivery_is_left_pending(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: FailingHandler(RuntimeError("redis down"))})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        result = harness.run()

        assert result == BatchResult(retried=1)
        assert harness.pending == 1

    def test_it_is_not_parked(self) -> None:
        """Parking a transient fault would silently discard a notification a user wanted."""
        harness = Harness(handlers={ORDER_CONFIRMED: FailingHandler(TimeoutError())})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert harness.parked_reasons == []

    def test_the_reclaim_pass_hands_it_back(self) -> None:
        handler = FailingHandler(RuntimeError("redis down"))
        harness = Harness(handlers={ORDER_CONFIRMED: handler})
        harness.publish(COMMERCE_ORDER_CONFIRMED)
        harness.run()

        harness.dispatcher.reclaim_once(count=10, schedule=NO_BACKOFF)

        assert handler.calls == 2

    def test_a_persistently_failing_event_is_eventually_parked(self) -> None:
        """The self-correcting half of the asymmetry: guessing "transient" costs retries."""
        handler = FailingHandler(RuntimeError("still down"))
        harness = Harness(handlers={ORDER_CONFIRMED: handler}, max_attempts=3)
        harness.publish(COMMERCE_ORDER_CONFIRMED)
        harness.run()

        for _ in range(5):
            harness.dispatcher.reclaim_once(count=10, schedule=NO_BACKOFF)

        assert handler.calls == 3
        assert harness.pending == 0
        assert "retry budget exhausted" in harness.parked_reasons[0]


class TestAPermanentFailureIsParkedAndAcked:
    def test_a_handler_raising_an_event_error_parks_the_delivery(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: FailingHandler(MalformedEvent("no orderId"))})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        result = harness.run()

        assert result == BatchResult(dead_lettered=1)
        assert harness.pending == 0
        assert "no orderId" in harness.parked_reasons[0]

    def test_an_unsupported_event_from_a_handler_is_also_permanent(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: FailingHandler(UnsupportedEvent("v9"))})
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        assert harness.run() == BatchResult(dead_lettered=1)

    def test_an_unparseable_payload_is_parked_with_its_bytes_intact(self) -> None:
        """The parked copy is the only reproducible record of what actually failed."""
        harness = Harness()
        harness.publish("{ this is not json")

        result = harness.run()

        assert result == BatchResult(dead_lettered=1)
        assert harness.sink.parked[0].delivery.payload == "{ this is not json"  # type: ignore[attr-defined]

    def test_an_unsupported_schema_version_is_parked(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})
        harness.publish(envelope(schemaVersion=2))

        result = harness.run()

        assert result == BatchResult(dead_lettered=1)
        assert "not understood by this build" in harness.parked_reasons[0]

    def test_an_unsupported_version_never_reaches_the_handler(self) -> None:
        """The entire point: a changed meaning must not be guessed at."""
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler})
        harness.publish(envelope(schemaVersion=2))

        harness.run()

        assert handler.seen == []

    def test_a_payload_missing_required_fields_is_parked(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})
        harness.publish(envelope(data={"orderId": "o-1"}))

        result = harness.run()

        assert result == BatchResult(dead_lettered=1)
        assert "missing required data field" in harness.parked_reasons[0]


class TestEventsThatAreNotOurs:
    """Acked without being parked -- a queue that alarms on normal traffic is unread."""

    def test_an_unknown_event_type_is_dropped(self) -> None:
        harness = Harness()
        harness.publish(envelope(type="loyalty.points_awarded"))

        result = harness.run()

        assert result == BatchResult(dropped=1)
        assert harness.pending == 0
        assert harness.parked_reasons == []

    def test_a_known_type_with_no_handler_is_dropped(self) -> None:
        """NTF-201 ships exactly this state: the framework runs, nothing is plugged in."""
        harness = Harness()
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        result = harness.run()

        assert result == BatchResult(dropped=1)
        assert harness.pending == 0
        assert harness.parked_reasons == []


class TestTheRetryBudget:
    def test_a_delivery_past_the_budget_is_parked_without_being_handled(self) -> None:
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler}, max_attempts=2)

        result = harness.dispatcher.dispatch(
            DeliveredEvent("1", json.dumps(COMMERCE_ORDER_CONFIRMED), attempt=3)
        )

        assert result == BatchResult(dead_lettered=1)
        assert handler.seen == []
        assert "retry budget exhausted after 3 deliveries" in harness.parked_reasons[0]

    def test_a_delivery_at_the_budget_is_still_attempted(self) -> None:
        """Off-by-one here would silently cost every event its last retry."""
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler}, max_attempts=2)

        harness.dispatcher.dispatch(
            DeliveredEvent("1", json.dumps(COMMERCE_ORDER_CONFIRMED), attempt=2)
        )

        assert len(handler.seen) == 1

    def test_a_budget_below_one_is_clamped(self) -> None:
        """A misconfigured zero would park every event on first delivery."""
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler}, max_attempts=0)
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert len(handler.seen) == 1


class TestParkingHappensBeforeAcking:
    def test_a_sink_failure_leaves_the_delivery_pending(self) -> None:
        """Acking first would settle the message and *then* lose it."""
        harness = Harness(dead_letters=ExplodingSink())
        harness.publish("not json")

        with pytest.raises(RuntimeError, match="dead-letter store is down"):
            harness.run()

        assert harness.pending == 1


class TestHandlerRegistration:
    def test_a_handler_can_be_registered_after_construction(self) -> None:
        """Which is how NTF-202 attaches its order handlers to the built dispatcher."""
        handler = RecordingHandler()
        harness = Harness()
        harness.dispatcher.register(ORDER_CONFIRMED, handler)
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert len(handler.seen) == 1

    def test_registering_two_handlers_for_one_type_is_refused(self) -> None:
        """Silent replacement would leave the first handler never running, with no error."""
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})

        with pytest.raises(ValueError, match="already registered"):
            harness.dispatcher.register(ORDER_CONFIRMED, RecordingHandler())

    def test_the_dispatcher_reports_what_it_handles(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})

        assert harness.dispatcher.handled_types == (ORDER_CONFIRMED,)

    def test_a_fresh_dispatcher_handles_nothing(self) -> None:
        assert Harness().dispatcher.handled_types == ()


class TestBatchAccounting:
    def test_a_mixed_batch_is_counted_by_outcome(self) -> None:
        harness = Harness(handlers={ORDER_CONFIRMED: RecordingHandler()})
        harness.publish(COMMERCE_ORDER_CONFIRMED)
        harness.publish(envelope(type="loyalty.points_awarded"))
        harness.publish("not json")
        harness.publish(envelope(schemaVersion=99))

        result = harness.run()

        assert result == BatchResult(handled=1, dropped=1, dead_lettered=2)
        assert result.total == 4

    def test_an_empty_poll_settles_nothing(self) -> None:
        assert Harness().run() == BatchResult()

    def test_results_accumulate(self) -> None:
        assert BatchResult(handled=1, dropped=2) + BatchResult(handled=3, retried=1) == (
            BatchResult(handled=4, dropped=2, retried=1)
        )

    def test_one_failure_does_not_stop_the_rest_of_the_batch(self) -> None:
        """A poison message in position one must not strand the nine behind it."""
        handler = RecordingHandler()
        harness = Harness(handlers={ORDER_CONFIRMED: handler})
        harness.publish("not json")
        harness.publish(COMMERCE_ORDER_CONFIRMED)

        harness.run()

        assert len(handler.seen) == 1


class TestSubscribing:
    def test_ensure_subscribed_creates_the_group(self) -> None:
        """Deferred out of the constructor so building a dispatcher touches no network."""
        consumer = InMemoryEventConsumer()
        dispatcher = EventDispatcher(
            consumer, registry=default_registry(), dead_letters=InMemoryDeadLetterQueue()
        )
        consumer.publish(COMMERCE_ORDER_CONFIRMED)

        dispatcher.ensure_subscribed()
        consumer.publish(envelope(id="after"))

        assert dispatcher.poll_once(count=10, block_ms=0) == BatchResult(dropped=1)
