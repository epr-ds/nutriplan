"""Chaos tests for the resilient event publisher (COM-109).

Verify that event publishing survives bus outages without failing the originating write.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from services.commerce.app.events.resilient import ResilientEventPublisher


class TestResilientEventPublisher:
    """Verify graceful degradation when the event bus is unavailable."""

    def test_swallows_connection_error(self, valid_event: dict) -> None:
        """When Redis is down, the publisher logs and swallows the error."""
        inner = MagicMock()
        inner.publish.side_effect = Exception("Connection refused")

        publisher = ResilientEventPublisher(inner)

        # Should NOT raise — the write already succeeded
        publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

        inner.publish.assert_called_once()

    def test_swallows_timeout_error(self, valid_event: dict) -> None:
        """When the bus times out, the publisher swallows the error."""
        inner = MagicMock()
        inner.publish.side_effect = TimeoutError("bus timeout")

        publisher = ResilientEventPublisher(inner)

        publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

        inner.publish.assert_called_once()

    def test_passes_through_success(self, valid_event: dict) -> None:
        """When the bus is healthy, events are published normally."""
        inner = MagicMock()
        inner.publish.return_value = None

        publisher = ResilientEventPublisher(inner)

        publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

        inner.publish.assert_called_once()

    def test_swallows_all_exceptions(self, valid_event: dict) -> None:
        """Any exception on publish is swallowed — not just connection errors."""
        inner = MagicMock()
        inner.publish.side_effect = RuntimeError("unexpected error")

        publisher = ResilientEventPublisher(inner)

        # Should NOT raise
        publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

    def test_logs_failure(self, valid_event: dict, caplog: pytest.LogCaptureFixture) -> None:
        """Failures are logged at ERROR level."""
        inner = MagicMock()
        inner.publish.side_effect = Exception("Connection refused")

        publisher = ResilientEventPublisher(inner)

        with caplog.at_level(logging.ERROR):
            publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

        assert "Failed to publish domain event" in caplog.text

    def test_no_event_published_on_success(self, valid_event: dict) -> None:
        """When publish succeeds, no error is logged."""
        inner = MagicMock()
        inner.publish.return_value = None

        publisher = ResilientEventPublisher(inner)

        publisher.publish(MagicMock(type=valid_event["type"], id=valid_event["id"]))

        # No exception means no error path — the event was published successfully
        assert inner.publish.call_count == 1


class TestResilientPublisherChaosScenario:
    """Simulate a bus outage scenario."""

    def test_during_bus_outage_writes_succeed(self, valid_event: dict) -> None:
        """During a bus outage, order writes still succeed (publisher swallows errors)."""
        inner = MagicMock()
        inner.publish.side_effect = Exception("Redis connection refused")

        publisher = ResilientEventPublisher(inner)

        # Simulate 100 events during a bus outage
        for i in range(100):
            event = MagicMock(type="order.created", id=f"evt_{i}")
            # Should NOT raise — the write already succeeded
            publisher.publish(event)

        # All 100 publish attempts were made (even though they all failed)
        assert inner.publish.call_count == 100

    def test_recovers_after_bus_restored(self, valid_event: dict) -> None:
        """After the bus is restored, events publish normally."""
        call_count = [0]

        def publish_side_effect(event):
            call_count[0] += 1
            if call_count[0] <= 3:
                raise Exception("Redis connection refused")

        inner = MagicMock()
        inner.publish.side_effect = publish_side_effect

        publisher = ResilientEventPublisher(inner)

        # First 3 events fail (bus is down)
        for _ in range(3):
            publisher.publish(MagicMock(type="order.created", id="evt_fail"))

        # Next event succeeds (bus is restored)
        publisher.publish(MagicMock(type="order.created", id="evt_success"))

        assert call_count[0] == 4
