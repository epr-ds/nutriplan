"""COM-407: the per-provider circuit breaker, its telemetry, registry, and adapter decorator.

Pure unit tests -- no HTTP, no database, no sleeping. The breaker's clock is injected so cooldowns
are driven deterministically, and the decorator is exercised against a stub adapter that counts
calls, which is how "an open circuit does not touch the provider" is asserted.
"""

from __future__ import annotations

import pytest

from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery_catalog import (
    GroceryOrderLine,
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GrocerySearchItem,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.circuit_breaker import (
    BreakerPolicy,
    BreakerState,
    CircuitBreaker,
    CircuitBreakerRegistry,
    InMemoryBreakerTelemetry,
    LoggingBreakerTelemetry,
)
from app.grocery.resilient import CircuitBreakingGroceryAdapter

PROVIDER = "freshbasket"
QUERY = GrocerySearchQuery(zip_code="06700", items=(GrocerySearchItem(ingredient="milk"),))
ORDER = GroceryOrderRequest(
    provider_id=PROVIDER,
    reference="ord-1",
    zip_code="06700",
    lines=(GroceryOrderLine(sku="fb-milk-1l", quantity=2),),
)


class _Clock:
    """A hand-cranked monotonic clock so cooldowns are exercised without waiting."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _StubAdapter:
    """A grocery adapter that succeeds or fails on demand and counts every call it receives."""

    def __init__(self, provider_id: str = PROVIDER, *, failing: bool = False) -> None:
        self._provider_id = provider_id
        self.failing = failing
        self.calls = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        self._record()
        return GrocerySearchResult(provider_id=self._provider_id, products=())

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        self._record()
        return GroceryOrderPlacement(
            provider_id=self._provider_id,
            external_order_id="ext-1",
            status=GroceryOrderStatus.PENDING,
        )

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        self._record()
        return GroceryOrderStatus.CONFIRMED

    def _record(self) -> None:
        self.calls += 1
        if self.failing:
            raise GroceryProviderUnavailableError(self._provider_id, "upstream exploded")


def _breaker(
    *,
    threshold: int = 3,
    reset: float = 30.0,
    clock: _Clock | None = None,
    telemetry: InMemoryBreakerTelemetry | None = None,
) -> tuple[CircuitBreaker, _Clock, InMemoryBreakerTelemetry]:
    clock = clock or _Clock()
    telemetry = telemetry or InMemoryBreakerTelemetry()
    breaker = CircuitBreaker(
        PROVIDER,
        policy=BreakerPolicy(failure_threshold=threshold, reset_timeout_seconds=reset),
        telemetry=telemetry,
        clock=clock,
    )
    return breaker, clock, telemetry


# --- policy -----------------------------------------------------------------------------------


def test_policy_defaults_are_sane():
    policy = BreakerPolicy()
    assert policy.failure_threshold >= 1
    assert policy.reset_timeout_seconds > 0


@pytest.mark.parametrize(
    ("threshold", "reset"),
    [(0, 30.0), (-1, 30.0), (3, 0.0), (3, -5.0)],
)
def test_policy_rejects_impossible_values(threshold, reset):
    with pytest.raises(ValueError):
        BreakerPolicy(failure_threshold=threshold, reset_timeout_seconds=reset)


# --- state machine ----------------------------------------------------------------------------


def test_a_new_breaker_is_closed_and_allows_calls():
    breaker, _, _ = _breaker()

    assert breaker.state is BreakerState.CLOSED
    assert breaker.allows() is True


def test_failures_below_the_threshold_keep_the_circuit_closed():
    breaker, _, _ = _breaker(threshold=3)

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state is BreakerState.CLOSED
    assert breaker.allows() is True


def test_the_circuit_opens_at_the_failure_threshold():
    breaker, _, _ = _breaker(threshold=3)

    for _ in range(3):
        breaker.record_failure()

    assert breaker.state is BreakerState.OPEN
    assert breaker.allows() is False


def test_a_success_resets_the_failure_streak():
    breaker, _, _ = _breaker(threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state is BreakerState.CLOSED
    assert breaker.snapshot().consecutive_failures == 2


def test_an_open_circuit_stays_closed_to_traffic_until_the_reset_window_elapses():
    breaker, clock, _ = _breaker(threshold=1, reset=30.0)
    breaker.record_failure()

    clock.advance(29.0)

    assert breaker.allows() is False
    assert breaker.state is BreakerState.OPEN


def test_a_cooled_down_circuit_admits_exactly_one_half_open_probe():
    breaker, clock, _ = _breaker(threshold=1, reset=30.0)
    breaker.record_failure()

    clock.advance(30.0)

    assert breaker.allows() is True
    assert breaker.state is BreakerState.HALF_OPEN
    # The probe is in flight: a concurrent caller must not stampede the recovering provider.
    assert breaker.allows() is False


def test_a_successful_probe_closes_the_circuit():
    breaker, clock, _ = _breaker(threshold=1, reset=30.0)
    breaker.record_failure()
    clock.advance(30.0)
    breaker.allows()

    breaker.record_success()

    assert breaker.state is BreakerState.CLOSED
    assert breaker.allows() is True


def test_a_failed_probe_reopens_the_circuit_for_another_full_window():
    breaker, clock, _ = _breaker(threshold=3, reset=30.0)
    for _ in range(3):
        breaker.record_failure()
    clock.advance(30.0)
    breaker.allows()

    breaker.record_failure()

    assert breaker.state is BreakerState.OPEN
    assert breaker.allows() is False
    clock.advance(29.0)
    assert breaker.allows() is False
    clock.advance(1.0)
    assert breaker.allows() is True


# --- observability ----------------------------------------------------------------------------


def test_the_snapshot_reports_state_failures_and_time_until_retry():
    breaker, clock, _ = _breaker(threshold=2, reset=30.0)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(10.0)

    snapshot = breaker.snapshot()

    assert snapshot.provider_id == PROVIDER
    assert snapshot.state is BreakerState.OPEN
    assert snapshot.consecutive_failures == 2
    assert snapshot.seconds_until_retry == pytest.approx(20.0)


def test_a_closed_circuit_reports_no_retry_delay():
    breaker, _, _ = _breaker()

    snapshot = breaker.snapshot()

    assert snapshot.state is BreakerState.CLOSED
    assert snapshot.seconds_until_retry == 0.0


def test_every_transition_is_reported_to_telemetry():
    breaker, clock, telemetry = _breaker(threshold=2, reset=30.0)

    breaker.record_failure()
    breaker.record_failure()  # closed -> open
    clock.advance(30.0)
    breaker.allows()  # open -> half_open
    breaker.record_success()  # half_open -> closed

    assert [(t.from_state, t.to_state) for t in telemetry.transitions] == [
        (BreakerState.CLOSED, BreakerState.OPEN),
        (BreakerState.OPEN, BreakerState.HALF_OPEN),
        (BreakerState.HALF_OPEN, BreakerState.CLOSED),
    ]
    assert telemetry.count_into(BreakerState.OPEN) == 1
    assert all(t.provider_id == PROVIDER for t in telemetry.transitions)


def test_telemetry_records_the_failure_count_that_tripped_the_circuit():
    breaker, _, telemetry = _breaker(threshold=3)

    for _ in range(3):
        breaker.record_failure()

    assert telemetry.transitions[0].consecutive_failures == 3


def test_a_quiet_breaker_reports_nothing():
    _, _, telemetry = _breaker()

    assert telemetry.transitions == ()
    assert telemetry.count_into(BreakerState.OPEN) == 0


def test_the_logging_telemetry_warns_when_a_circuit_opens(caplog):
    breaker = CircuitBreaker(
        PROVIDER,
        policy=BreakerPolicy(failure_threshold=1, reset_timeout_seconds=30.0),
        telemetry=LoggingBreakerTelemetry(),
    )

    with caplog.at_level("INFO"):
        breaker.record_failure()

    assert any(
        record.levelname == "WARNING" and PROVIDER in record.getMessage()
        for record in caplog.records
    )


# --- registry ---------------------------------------------------------------------------------


def test_the_registry_returns_the_same_breaker_for_a_provider():
    registry = CircuitBreakerRegistry()

    assert registry.for_provider(PROVIDER) is registry.for_provider(PROVIDER)


def test_breakers_are_isolated_per_provider():
    registry = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=1))

    registry.for_provider(PROVIDER).record_failure()

    assert registry.for_provider(PROVIDER).state is BreakerState.OPEN
    assert registry.for_provider("walmart").state is BreakerState.CLOSED


def test_the_registry_snapshot_reports_every_known_provider_by_id():
    registry = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=1))
    registry.for_provider("walmart")
    registry.for_provider(PROVIDER).record_failure()

    snapshots = registry.snapshot()

    assert [s.provider_id for s in snapshots] == ["freshbasket", "walmart"]
    assert {s.provider_id: s.state for s in snapshots} == {
        "freshbasket": BreakerState.OPEN,
        "walmart": BreakerState.CLOSED,
    }


def test_an_untouched_registry_snapshot_is_empty():
    assert CircuitBreakerRegistry().snapshot() == ()


def test_the_registry_hands_its_policy_and_clock_to_each_breaker():
    clock = _Clock()
    registry = CircuitBreakerRegistry(
        policy=BreakerPolicy(failure_threshold=1, reset_timeout_seconds=10.0), clock=clock
    )
    breaker = registry.for_provider(PROVIDER)

    breaker.record_failure()
    clock.advance(10.0)

    assert breaker.allows() is True


# --- the adapter decorator --------------------------------------------------------------------


def test_the_decorator_satisfies_the_grocery_provider_port():
    breaker, _, _ = _breaker()
    adapter = CircuitBreakingGroceryAdapter(_StubAdapter(), breaker)

    assert isinstance(adapter, GroceryProviderAdapter)
    assert adapter.provider_id == PROVIDER
    assert adapter.breaker is breaker


def test_a_closed_circuit_passes_calls_straight_through():
    breaker, _, _ = _breaker()
    inner = _StubAdapter()
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)

    assert adapter.search(QUERY).provider_id == PROVIDER
    assert adapter.place_order(ORDER).external_order_id == "ext-1"
    assert adapter.get_order_status("ext-1") is GroceryOrderStatus.CONFIRMED
    assert inner.calls == 3
    assert breaker.state is BreakerState.CLOSED


def test_provider_failures_trip_the_circuit_and_are_re_raised():
    breaker, _, _ = _breaker(threshold=2)
    inner = _StubAdapter(failing=True)
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)

    for _ in range(2):
        with pytest.raises(GroceryProviderUnavailableError):
            adapter.search(QUERY)

    assert inner.calls == 2
    assert breaker.state is BreakerState.OPEN


def test_an_open_circuit_fails_fast_without_calling_the_provider():
    breaker, _, _ = _breaker(threshold=1)
    inner = _StubAdapter(failing=True)
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)
    with pytest.raises(GroceryProviderUnavailableError):
        adapter.search(QUERY)
    assert inner.calls == 1

    with pytest.raises(GroceryProviderUnavailableError) as excinfo:
        adapter.search(QUERY)

    assert inner.calls == 1  # the provider was never touched
    assert excinfo.value.provider_id == PROVIDER
    assert "circuit open" in str(excinfo.value)


@pytest.mark.parametrize(
    "call",
    [
        lambda adapter: adapter.search(QUERY),
        lambda adapter: adapter.place_order(ORDER),
        lambda adapter: adapter.get_order_status("ext-1"),
    ],
)
def test_every_port_operation_is_guarded_by_the_circuit(call):
    breaker, _, _ = _breaker(threshold=1)
    breaker.record_failure()
    inner = _StubAdapter()
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)

    with pytest.raises(GroceryProviderUnavailableError):
        call(adapter)

    assert inner.calls == 0


def test_a_recovered_provider_closes_the_circuit_through_the_decorator():
    breaker, clock, _ = _breaker(threshold=1, reset=30.0)
    inner = _StubAdapter(failing=True)
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)
    with pytest.raises(GroceryProviderUnavailableError):
        adapter.search(QUERY)
    clock.advance(30.0)
    inner.failing = False

    adapter.search(QUERY)

    assert breaker.state is BreakerState.CLOSED
    assert inner.calls == 2


def test_a_still_broken_provider_reopens_the_circuit_on_its_probe():
    breaker, clock, _ = _breaker(threshold=1, reset=30.0)
    inner = _StubAdapter(failing=True)
    adapter = CircuitBreakingGroceryAdapter(inner, breaker)
    with pytest.raises(GroceryProviderUnavailableError):
        adapter.search(QUERY)
    clock.advance(30.0)

    with pytest.raises(GroceryProviderUnavailableError):
        adapter.search(QUERY)  # the probe

    assert inner.calls == 2
    assert breaker.state is BreakerState.OPEN


def test_an_unexpected_error_propagates_without_tripping_the_circuit():
    # Only GroceryProviderUnavailableError means "the provider is unhealthy"; anything else is a
    # bug on our side of the ACL and must not take a provider out of rotation.
    class _Buggy(_StubAdapter):
        def search(self, query):
            raise RuntimeError("boom")

    breaker, _, telemetry = _breaker(threshold=1)
    adapter = CircuitBreakingGroceryAdapter(_Buggy(), breaker)

    with pytest.raises(RuntimeError):
        adapter.search(QUERY)

    assert breaker.state is BreakerState.CLOSED
    assert telemetry.transitions == ()
