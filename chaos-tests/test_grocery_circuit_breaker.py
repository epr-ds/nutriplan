"""Chaos tests for the grocery circuit breaker (COM-407).

Inject failures into grocery provider calls and verify:
1. Circuit opens after failure_threshold consecutive failures
2. Circuit fails fast (no network calls) when open
3. Circuit recovers after cooldown (half-open probe succeeds)
4. Circuit re-opens if half-open probe fails
"""

from __future__ import annotations

import time

import pytest

from services.commerce.app.grocery.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerRegistry,
    InMemoryBreakerTelemetry,
)
from services.commerce.app.grocery.resilient import CircuitBreakingGroceryAdapter
from services.commerce.app.domain.errors import GroceryProviderUnavailableError


class FailingGroceryAdapter:
    """A grocery adapter that fails on demand."""

    def __init__(self, provider_id: str, should_fail: bool = False) -> None:
        self.provider_id = provider_id
        self._should_fail = should_fail
        self.call_count = 0

    def search(self, query: Any) -> Any:
        self.call_count += 1
        if self._should_fail:
            raise GroceryProviderUnavailableError(
                self.provider_id, "provider is down"
            )
        return {"results": []}

    def place_order(self, request: Any) -> Any:
        self.call_count += 1
        if self._should_fail:
            raise GroceryProviderUnavailableError(
                self.provider_id, "provider is down"
            )
        return {"order_id": "ext_123"}

    def get_order_status(self, external_order_id: str) -> Any:
        self.call_count += 1
        if self._should_fail:
            raise GroceryProviderUnavailableError(
                self.provider_id, "provider is down"
            )
        return {"status": "delivered"}


class TestGroceryCircuitBreakerOpens:
    """Verify the circuit opens after consecutive failures."""

    def test_opens_after_failure_threshold(self, fake_clock: FakeClock) -> None:
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "chedraui",
            policy=type("Policy", (), {"failure_threshold": 3, "reset_timeout_seconds": 30.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )
        adapter = FailingGroceryAdapter("chedraui", should_fail=True)
        wrapped = CircuitBreakingGroceryAdapter(adapter, breaker)

        # Each failure advances the breaker
        for i in range(3):
            with pytest.raises(GroceryProviderUnavailableError):
                wrapped.search(None)

        assert breaker.state is BreakerState.OPEN
        assert telemetry.count_into(BreakerState.OPEN) == 1

    def test_fails_fast_when_open(self, fake_clock: FakeClock) -> None:
        """Once open, no network calls are made — just fail fast."""
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "walmart",
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 30.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )
        adapter = FailingGroceryAdapter("walmart", should_fail=True)
        wrapped = CircuitBreakingGroceryAdapter(adapter, breaker)

        # Trip the breaker
        for _ in range(2):
            with pytest.raises(GroceryProviderUnavailableError):
                wrapped.search(None)

        assert breaker.state is BreakerState.OPEN

        # Subsequent calls fail fast without calling the adapter
        initial_calls = adapter.call_count
        with pytest.raises(GroceryProviderUnavailableError):
            wrapped.search(None)

        # Adapter was NOT called — fail fast
        assert adapter.call_count == initial_calls

    def test_records_transitions(self, fake_clock: FakeClock) -> None:
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "freshbasket",
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 30.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()

        transitions = telemetry.transitions
        assert len(transitions) == 1
        assert transitions[0].from_state is BreakerState.CLOSED
        assert transitions[0].to_state is BreakerState.OPEN
        assert transitions[0].consecutive_failures == 2


class TestGroceryCircuitBreakerRecovery:
    """Verify the circuit recovers after cooldown."""

    def test_recovers_after_cooldown(self, fake_clock: FakeClock) -> None:
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "chedraui",
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 10.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state is BreakerState.OPEN

        # Advance past cooldown
        fake_clock.advance(11.0)

        # Half-open probe succeeds
        assert breaker.allows() is True  # promotes to HALF_OPEN
        breaker.record_success()
        assert breaker.state is BreakerState.CLOSED

    def test_half_open_admits_one_probe(self, fake_clock: FakeClock) -> None:
        """Only one probe is admitted per cooldown period."""
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "walmart",
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 10.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()

        # Advance past cooldown
        fake_clock.advance(11.0)

        # First call promotes to HALF_OPEN
        assert breaker.allows() is True
        assert breaker.state is BreakerState.HALF_OPEN

        # Second call is refused (probe already in flight)
        assert breaker.allows() is False

    def test_half_open_probe_fails_reopens(self, fake_clock: FakeClock) -> None:
        """If the half-open probe fails, the circuit re-opens."""
        telemetry = InMemoryBreakerTelemetry()
        breaker = CircuitBreaker(
            "freshbasket",
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 10.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()

        # Advance past cooldown
        fake_clock.advance(11.0)

        # Probe fails
        assert breaker.allows() is True
        breaker.record_failure()
        assert breaker.state is BreakerState.OPEN

        # Another transition to OPEN
        assert telemetry.count_into(BreakerState.OPEN) == 2


class TestGroceryCircuitBreakerRegistry:
    """Verify the registry manages per-provider breakers."""

    def test_separate_breakers_per_provider(
        self, fake_clock: FakeClock, grocery_providers: list[str]
    ) -> None:
        telemetry = InMemoryBreakerTelemetry()
        registry = CircuitBreakerRegistry(
            policy=type("Policy", (), {"failure_threshold": 2, "reset_timeout_seconds": 10.0})(),
            telemetry=telemetry,
            clock=fake_clock,
        )

        for provider in grocery_providers:
            breaker = registry.for_provider(provider)
            breaker.record_failure()
            breaker.record_failure()

        # All three should be open
        snapshots = registry.snapshot()
        assert len(snapshots) == 3
        for snap in snapshots:
            assert snap.state is BreakerState.OPEN

    def test_snapshot_ordered_by_provider_id(
        self, fake_clock: FakeClock, grocery_providers: list[str]
    ) -> None:
        registry = CircuitBreakerRegistry(
            clock=fake_clock,
        )

        # Add in non-alphabetical order
        for provider in reversed(grocery_providers):
            registry.for_provider(provider)

        snapshots = registry.snapshot()
        provider_ids = [s.provider_id for s in snapshots]
        assert provider_ids == sorted(grocery_providers)
