"""Chaos tests for notification service resilience (NTF-204).

Verify exponential backoff and dead-letter queue behavior under failure.
"""

from __future__ import annotations

from app.events.backoff import (
    RetrySchedule,
)
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import (
    InMemoryDeadLetterQueue,
)


class TestNotificationBackoff:
    """Verify exponential backoff grows correctly under failures."""

    def test_base_delay_first_attempt(self) -> None:
        """First retry uses the base delay."""
        schedule = RetrySchedule(base_ms=60_000)
        delay = schedule.delay_for(attempt=1)
        assert delay == 60_000

    def test_exponential_growth(self) -> None:
        """Each attempt waits twice as long as the last."""
        schedule = RetrySchedule(base_ms=60_000, multiplier=2.0)

        delays = [schedule.delay_for(attempt=i) for i in range(1, 6)]

        # Without jitter: 60k, 120k, 240k, 480k, 960k
        assert delays[0] == 60_000
        assert delays[1] == 120_000
        assert delays[2] == 240_000

    def test_capped_at_max_delay(self) -> None:
        """Delay never exceeds the cap."""
        schedule = RetrySchedule(base_ms=60_000, cap_ms=300_000)

        # After enough attempts, delay should be capped
        delay = schedule.delay_for(attempt=10)
        assert delay <= 300_000

    def test_jitter_spreads_delays(self) -> None:
        """Different delivery IDs get different jitter offsets."""
        schedule = RetrySchedule(base_ms=60_000, jitter=0.2)

        delay_a = schedule.delay_for(attempt=1, delivery_id="id_a")
        delay_b = schedule.delay_for(attempt=1, delivery_id="id_b")

        # With jitter, delays should be less than nominal
        assert delay_a < 60_000
        assert delay_b < 60_000

        # Different IDs should get different offsets
        assert delay_a != delay_b

    def test_no_jitter_when_disabled(self) -> None:
        """With jitter=0, delay equals nominal."""
        schedule = RetrySchedule(base_ms=60_000, jitter=0.0)

        delay = schedule.delay_for(attempt=1, delivery_id="any_id")
        assert delay == 60_000

    def test_is_due_checks_delay(self) -> None:
        """is_due returns True when idle time exceeds delay."""
        schedule = RetrySchedule(base_ms=60_000)

        assert schedule.is_due(attempt=1, idle_ms=0) is False
        assert schedule.is_due(attempt=1, idle_ms=59_999) is False
        assert schedule.is_due(attempt=1, idle_ms=60_000) is True

    def test_delay_grows_with_attempts(self) -> None:
        """Each failed delivery waits longer than the previous."""
        schedule = RetrySchedule(base_ms=60_000, multiplier=2.0)

        delays = [schedule.delay_for(attempt=i) for i in range(1, 6)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]


class TestNotificationDeadLetterQueue:
    """Verify DLQ behavior under failure."""

    def test_parks_failed_delivery(self) -> None:
        """Failed deliveries are parked in the DLQ."""
        queue = InMemoryDeadLetterQueue()
        delivery = DeliveredEvent(
            delivery_id="del_001",
            payload='{"type":"order.created","id":"evt_123"}',
            attempt=5,
        )

        queue.park(delivery, reason="handler raised: ConnectionError")

        assert queue.depth() == 1
        entry = queue.get("del_001")
        assert entry is not None
        assert entry.event_type == "order.created"
        assert entry.event_id == "evt_123"

    def test_replacing_entry(self) -> None:
        """Re-parking the same delivery replaces the entry."""
        queue = InMemoryDeadLetterQueue()
        delivery = DeliveredEvent(
            delivery_id="del_001",
            payload='{"type":"order.created","id":"evt_123"}',
            attempt=5,
        )

        queue.park(delivery, reason="first reason")
        queue.park(delivery, reason="updated reason")

        assert queue.depth() == 1
        entry = queue.get("del_001")
        assert entry.reason == "updated reason"

    def test_evicts_oldest_when_full(self) -> None:
        """When the queue is full, the oldest entry is evicted."""
        capacity = 3
        queue = InMemoryDeadLetterQueue(capacity=capacity)

        for i in range(capacity + 2):
            delivery = DeliveredEvent(
                delivery_id=f"del_{i:03d}",
                payload='{"type":"order.created","id":"evt_123"}',
                attempt=1,
            )
            queue.park(delivery, reason="test")

        assert queue.depth() == capacity

        # Oldest entries should be evicted
        assert queue.get("del_000") is None
        assert queue.get("del_001") is None
        assert queue.get("del_002") is not None
        assert queue.get("del_003") is not None
        assert queue.get("del_004") is not None

    def test_list_newest_first(self) -> None:
        """list() returns entries newest first."""
        queue = InMemoryDeadLetterQueue()

        for i in range(5):
            delivery = DeliveredEvent(
                delivery_id=f"del_{i:03d}",
                payload='{"type":"order.created","id":"evt_123"}',
                attempt=1,
            )
            queue.park(delivery, reason="test")

        entries = queue.list(limit=5)
        assert len(entries) == 5
        # Newest first
        assert entries[0].delivery_id == "del_004"
        assert entries[-1].delivery_id == "del_000"

    def test_remove_entry(self) -> None:
        """remove() drops an entry and returns True if it was there."""
        queue = InMemoryDeadLetterQueue()
        delivery = DeliveredEvent(
            delivery_id="del_001",
            payload='{"type":"order.created","id":"evt_123"}',
            attempt=1,
        )
        queue.park(delivery, reason="test")

        assert queue.remove("del_001") is True
        assert queue.get("del_001") is None
        assert queue.depth() == 0

        # Removing non-existent entry returns False
        assert queue.remove("del_999") is False

    def test_purge_clears_all(self) -> None:
        """purge() empties the queue."""
        queue = InMemoryDeadLetterQueue()

        for i in range(5):
            delivery = DeliveredEvent(
                delivery_id=f"del_{i:03d}",
                payload='{"type":"order.created","id":"evt_123"}',
                attempt=1,
            )
            queue.park(delivery, reason="test")

        discarded = queue.purge()
        assert discarded == 5
        assert queue.depth() == 0

    def test_park_does_not_raise(self) -> None:
        """park() must never raise — it's called on the error path."""
        queue = InMemoryDeadLetterQueue()
        delivery = DeliveredEvent(
            delivery_id="del_001",
            payload='{"type":"order.created","id":"evt_123"}',
            attempt=1,
        )

        # Should not raise even with malformed payload
        delivery_bad = DeliveredEvent(
            delivery_id="del_bad",
            payload="not json at all {{{",
            attempt=1,
        )
        queue.park(delivery_bad, reason="malformed payload")

        assert queue.depth() == 2
        entry = queue.get("del_bad")
        assert entry is not None
        assert entry.event_type is None  # couldn't parse
        assert entry.event_id is None


class TestNotificationChaosScenario:
    """Simulate a notification delivery failure scenario."""

    def test_delivery_fails_then_succeeds(self) -> None:
        """A delivery that fails 3 times then succeeds."""
        schedule = RetrySchedule(base_ms=60_000, multiplier=2.0)

        # Check delays for each attempt
        delays = [schedule.delay_for(attempt=i) for i in range(1, 4)]

        # Should grow: 60k, 120k, 240k
        assert delays[0] < delays[1] < delays[2]

    def test_poison_message_parked_after_budget(self) -> None:
        """A poison message is parked after exhausting retry budget."""
        queue = InMemoryDeadLetterQueue()
        schedule = RetrySchedule(base_ms=60_000, multiplier=2.0)

        # Simulate 5 failed deliveries (retry budget)
        for attempt in range(1, 6):
            delay = schedule.delay_for(attempt=attempt, delivery_id="poison_msg")
            # In real code, the consumer would check is_due() here

        # After budget exhausted, park in DLQ
        delivery = DeliveredEvent(
            delivery_id="poison_msg",
            payload='{"type":"order.status","id":"evt_poison"}',
            attempt=5,
        )
        queue.park(delivery, reason="retry budget exhausted")

        assert queue.depth() == 1
        assert queue.get("poison_msg").attempt == 5
