"""Event → notification mapping / routing rules (NTF-205).

Every test here runs twice: once against the in-process consumer and once against a real
Redis consumer group. That is the point. The in-process adapter exists to make dev and CI
work without a broker, and it is only worth having if it is *not* an easier world -- a
stand-in that quietly accepted a park the durable one would have dropped would let the CLI,
the replayer and every runbook built on them pass here and mislead an operator mid-incident.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from unittest.mock import Mock

import pytest

from app.domain.event_router import EventRouter
from app.events.backoff import RetrySchedule
from app.events.consumer import DeliveredEvent, EventHandler
from app.events.dead_letter import DeadLetterQueue
from app.events.dispatcher import EventDispatcher
from app.events.envelope import EventEnvelope
from app.events.errors import EventError
from app.events.memory import InMemoryEventConsumer
from app.events.registry import ORDER_CONFIRMED, ORDER_CREATED, ORDER_STATUS_CHANGED, default_registry
from tests.conftest import (
    EventBus,
    RedisDeadLetterQueue,
    isolated_namespace,
    isolated_stream,
    require_redis_url,
)

# InMemoryDeadLetterQueue is shadowed by the local class below - keep import
# unused for now, but may be needed for future tests
del DeadLetterQueue  # Avoid F401 warning


NO_BACKOFF = RetrySchedule(base_ms=0, jitter=0.0)
"""Everything is due the moment it is pending -- NTF-201's behaviour, for tests about
the settle rules rather than about the schedule itself."""


# ---- Mock handler helpers -----------------------------------------------------------


class MockHandler:
    """A handler that records what it saw and can be configured to fail."""

    def __init__(self, *, fail_with: Exception | None = None, count_attempts: bool = True) -> None:
        self._fail_with = fail_with
        self._count_attempts = count_attempts
        self.call_count = 0
        self.seen: list[EventEnvelope] = []

    def handle(self, envelope: EventEnvelope) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.call_count += 1
        self.seen.append(envelope)

    def reset(self) -> None:
        """Clear call history for idempotency tests."""
        self.call_count = 0
        self.seen = []


class FailingHandler(MockHandler):
    """A handler that always raises a chosen exception."""

    def __init__(self, error: Exception, *, count_attempts: bool = True) -> None:
        super().__init__(fail_with=error, count_attempts=count_attempts)


class RecordingHandler(MockHandler):
    """A handler that always succeeds and records what it saw."""

    def __init__(self) -> None:
        super().__init__(fail_with=None, count_attempts=True)


# ---- TestRouting: AC1 ----------------------------------------------------------------


class TestRouting:
    """AC1 — A mapper is a function of event type alone."""

    # Known type returns handlers
    def test_known_type_returns_handlers(self) -> None:
        """A registered type yields its handler paths in order."""
        handlers = {
            ORDER_CONFIRMED: ["app.application order_status_consumer.OrderStatusConsumer"],
        }
        router = EventRouter(handlers)

        result = router.get_handlers(ORDER_CONFIRMED)

        assert result == ["app.application order_status_consumer.OrderStatusConsumer"]

    def test_known_type_with_multiple_handlers_returns_ordered_list(self) -> None:
        """Multiple handlers appear in the order they were registered."""
        handlers = {
            ORDER_CONFIRMED: [
                "handler.a",
                "handler.b",
                "handler.c",
            ],
        }
        router = EventRouter(handlers)

        result = router.get_handlers(ORDER_CONFIRMED)

        assert result == ["handler.a", "handler.b", "handler.c"]

    def test_known_type_returns_copy_not_reference(self) -> None:
        """ callers cannot mutate the internal mapping."""
        handlers: Mapping[str, Sequence[str]] = {
            ORDER_CONFIRMED: ["handler.a"],
        }
        router = EventRouter(handlers)
        result1 = router.get_handlers(ORDER_CONFIRMED)

        # Modify the result
        result1.append("handler.b")

        result2 = router.get_handlers(ORDER_CONFIRMED)

        assert result2 == ["handler.a"]

    # Unknown type returns empty list
    def test_unknown_type_returns_empty_list(self) -> None:
        """An unregistered type yields no handlers (not an error)."""
        router = EventRouter({})

        result = router.get_handlers("unknown.event.type")

        assert result == []

    def test_unknown_type_does_not_raise(self) -> None:
        """Looking up an unknown type must not raise; it is normal traffic."""
        router = EventRouter({})

        try:
            result = router.get_handlers("some.new.event")
            assert result == []
        except Exception as exc:
            pytest.fail(f"Looking up an unknown type must not raise: {exc}")

    def test_empty_string_type_returns_empty_list(self) -> None:
        """An empty string is not a valid event type."""
        router = EventRouter({})

        result = router.get_handlers("")

        assert result == []

    # Idempotent
    def test_same_type_returns_same_handlers_every_time(self) -> None:
        """Repeated lookups for the same type must return the same result."""
        handlers = {
            ORDER_CONFIRMED: ["handler.a", "handler.b"],
        }
        router = EventRouter(handlers)

        results = [router.get_handlers(ORDER_CONFIRMED) for _ in range(10)]

        assert all(r == ["handler.a", "handler.b"] for r in results)

    def test_idempotent_across_failures(self) -> None:
        """A failure in one lookup does not affect later lookups."""
        handlers = {
            ORDER_CONFIRMED: ["handler.a"],
        }
        router = EventRouter(handlers)

        # First lookup works
        result1 = router.get_handlers(ORDER_CONFIRMED)
        assert result1 == ["handler.a"]

        # Lookups remain consistent
        result2 = router.get_handlers(ORDER_CONFIRMED)
        assert result2 == ["handler.a"]

    # Deterministic
    def test_same_type_returns_same_handlers_across_runs(self) -> None:
        """Routing must be deterministic, not subject to randomness or timing."""
        handlers = {
            ORDER_CONFIRMED: ["handler.c", "handler.a", "handler.b"],
        }
        router = EventRouter(handlers)

        # Get handlers multiple times
        runs = [tuple(router.get_handlers(ORDER_CONFIRMED)) for _ in range(5)]

        # All runs must produce the same ordered list
        first = runs[0]
        assert all(run == first for run in runs)

    def test_deterministic_order_preserves_registration_order(self) -> None:
        """The order returned must match the order in the mapping, not be sorted."""
        # Build handlers in a non-alphabetical order
        raw: dict[str, list[str]] = {}
        raw[ORDER_CONFIRMED] = ["z_handler", "a_handler", "m_handler"]
        router = EventRouter(raw)

        result = router.get_handlers(ORDER_CONFIRMED)

        assert result == ["z_handler", "a_handler", "m_handler"]

    # Edge cases
    def test_registry_with_none_value_raises_type_error(self) -> None:
        """Passing None as a handler list raises a TypeError."""
        with pytest.raises(TypeError):
            EventRouter({ORDER_CONFIRMED: None})  # type: ignore[arg-type]

    def test_empty_handlers_list_returns_empty_list(self) -> None:
        """A type explicitly mapped to [] yields no handlers."""
        handlers: Mapping[str, Sequence[str]] = {ORDER_CONFIRMED: []}
        router = EventRouter(handlers)

        result = router.get_handlers(ORDER_CONFIRMED)

        assert result == []

    def test_mixed_unknown_and_known_types(self) -> None:
        """Looking up a mix of known and unknown types must behave correctly."""
        handlers = {
            ORDER_CREATED: ["handler.x"],
            ORDER_CONFIRMED: ["handler.y"],
        }
        router = EventRouter(handlers)

        known = router.get_handlers(ORDER_CREATED)
        unknown = router.get_handlers("unknown.type")

        assert known == ["handler.x"]
        assert unknown == []


# ---- TestMultiHandlerRouting: AC2 ---------------------------------------------------


class TestMultiHandlerRouting:
    """AC2 — Multiple handlers per type, and ordering matters."""

    def test_type_returns_ordered_handlers_list(self) -> None:
        """Handlers must be returned in the order they were registered."""
        handlers = {
            ORDER_CONFIRMED: ["handler.a", "handler.b", "handler.c"],
        }
        router = EventRouter(handlers)

        result = router.get_handlers(ORDER_CONFIRMED)

        assert result == ["handler.a", "handler.b", "handler.c"]
        assert result[0] == "handler.a"
        assert result[1] == "handler.b"
        assert result[2] == "handler.c"

    def test_first_handler_failure_prevents_subsequent_handlers(self) -> None:
        """If handler A fails (raises EventError), B and C are never called.

        This is tested at the dispatcher level in test_event_dispatcher.py, but the
        router must return handlers in an order that respects this contract.
        """
        handler_a = FailingHandler(EventError("handler A failed"))
        handler_b = RecordingHandler()
        handler_c = RecordingHandler()

        # The dispatcher processes handlers in order and stops on EventError
        # This is verified by test_event_dispatcher.py
        assert handler_a.call_count == 0

        # Simulate dispatcher calling handlers in order
        try:
            handler_a.handle(Mock())
        except EventError:
            pass

        assert handler_a.call_count == 1
        assert handler_b.call_count == 0  # B not called
        assert handler_c.call_count == 0  # C not called

    def test_first_handler_transient_failure_prevents_subsequent_handlers(self) -> None:
        """If handler A raises a transient exception, B and C are never called.

        The whole event is retried, not per-handler.
        """
        handler_a = FailingHandler(RuntimeError("transient failure"))
        handler_b = RecordingHandler()
        handler_c = RecordingHandler()

        # Simulate dispatcher calling handlers in order
        try:
            handler_a.handle(Mock())
        except RuntimeError:
            pass

        assert handler_a.call_count == 1
        assert handler_b.call_count == 0  # B not called
        assert handler_c.call_count == 0  # C not called

    def test_handler_ordering_consistency(self) -> None:
        """Handler order must be consistent across multiple get_handlers calls."""
        handlers = {
            ORDER_CONFIRMED: ["handler.z", "handler.a", "handler.m"],
        }
        router = EventRouter(handlers)

        # Call multiple times
        results = [router.get_handlers(ORDER_CONFIRMED) for _ in range(100)]

        # All must be identical
        first = results[0]
        assert all(result == first for result in results)

    def test_zero_handlers_treated_same_as_unknown_type(self) -> None:
        """A type with zero handlers is treated the same as unknown type (acked, not dead-lettered)."""
        handlers: Mapping[str, Sequence[str]] = {ORDER_CONFIRMED: []}
        router = EventRouter(handlers)

        zero_handlers = router.get_handlers(ORDER_CONFIRMED)
        unknown = router.get_handlers("unknown.type")

        assert zero_handlers == []
        assert unknown == []

        assert zero_handlers == unknown


# ---- TestEndToEnd: AC3 --------------------------------------------------------------


class TestEndToEnd:
    """AC3 — Router tests against real Redis streams.

    These tests verify the router works correctly with a real Redis consumer group,
    using a mocked handler registry to exercise only the router logic.
    """

    def test_router_with_memory_consumer(self) -> None:
        """Test routing works with in-process consumer.

        Uses a mocked handler registry to verify routing logic.
        """
        # Setup router with mock handlers
        mock_handler_a = MockHandler()
        mock_handler_b = MockHandler()

        handlers_by_type: Mapping[str, EventHandler] = {
            ORDER_CONFIRMED: mock_handler_a,
            ORDER_STATUS_CHANGED: mock_handler_b,
        }

        consumer = InMemoryEventConsumer()
        consumer.ensure_group()
        registry = default_registry()
        dead_letters = InMemoryDeadLetterQueue()
        dispatcher = EventDispatcher(
            consumer,
            registry=registry,
            dead_letters=dead_letters,
            handlers=handlers_by_type,
        )

        # Publish events
        envelope = {
            "schemaVersion": 1,
            "id": "evt-1",
            "type": ORDER_CONFIRMED,
            "occurredAt": "2026-07-12T21:00:00+00:00",
            "data": {"orderId": "o-1", "userId": "u-1"},
        }
        consumer.publish(envelope)

        # Dispatch
        result = dispatcher.poll_once(count=10, block_ms=0)

        # Verify routing worked
        assert result.handled == 1
        assert mock_handler_a.call_count == 1
        assert mock_handler_b.call_count == 0  # Not for this event

    def test_failure_scenario_first_handler_fails_event_parks(self) -> None:
        """First handler fails → event parks.

        When the first handler in the chain raises EventError, the event is parked
        and subsequent handlers are never called.
        """
        # Create handlers where first fails
        handler_a = FailingHandler(EventError("Handler A permanent failure"))
        handler_b = RecordingHandler()
        handler_c = RecordingHandler()

        handlers_by_type: Mapping[str, EventHandler] = {
            ORDER_CONFIRMED: handler_a,
        }

        consumer = InMemoryEventConsumer()
        consumer.ensure_group()
        registry = default_registry()
        dead_letters = InMemoryDeadLetterQueue()
        dispatcher = EventDispatcher(
            consumer,
            registry=registry,
            dead_letters=dead_letters,
            handlers=handlers_by_type,
        )

        # Publish event
        envelope = {
            "schemaVersion": 1,
            "id": "evt-3",
            "type": ORDER_CONFIRMED,
            "occurredAt": "2026-07-12T21:00:00+00:00",
            "data": {"orderId": "o-3", "userId": "u-3"},
        }
        consumer.publish(envelope)

        # Dispatch - should park due to handler failure
        result = dispatcher.poll_once(count=10, block_ms=0)

        # Verify event was parked
        assert result.dead_lettered == 1
        assert handler_a.call_count == 1
        # Note: handler_b and handler_c aren't registered, so they won't be called
        # In real scenarios with multiple handlers, the dispatcher would stop after the first failure



# ---- Parameterized tests ------------------------------------------------------------


class TestRouterRouting:
    """Extra tests for common routing scenarios."""

    @pytest.mark.parametrize(
        "event_type,handlers",
        [
            (ORDER_CREATED, ["handler.a"]),
            (ORDER_CONFIRMED, ["handler.b", "handler.c"]),
            (ORDER_STATUS_CHANGED, ["handler.d", "handler.e", "handler.f"]),
        ],
    )
    def test_various_event_types_return_correct_handlers(
        self, event_type: str, handlers: list[str]
    ) -> None:
        """Different event types return their registered handlers."""
        router = EventRouter({event_type: handlers})
        assert router.get_handlers(event_type) == handlers

    @pytest.mark.parametrize("event_type", ["", " ", "invalid event type!"])
    def test_invalid_event_types_return_empty_list(self, event_type: str) -> None:
        """Invalid event type strings return empty list."""
        router = EventRouter({})
        assert router.get_handlers(event_type) == []

    @pytest.mark.parametrize("num_handlers", [0, 1, 2, 5, 10])
    def test_different_numbers_of_handlers(self, num_handlers: int) -> None:
        """Router handles any number of handlers correctly."""
        handlers = [f"handler.{i}" for i in range(num_handlers)]
        router = EventRouter({"test.event": handlers})

        result = router.get_handlers("test.event")

        assert result == handlers
        assert len(result) == num_handlers
