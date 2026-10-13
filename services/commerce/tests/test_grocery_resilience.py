"""COM-407: the wired resilience behaviour -- fallback, breaker lifetime, and observability.

Where ``test_grocery_circuit_breaker`` unit-tests the breaker in isolation, this module drives the
real composition: the fan-out skipping an open provider (the fallback), the process-wide breaker
registry outliving the per-request adapters, and the breaker state surfacing on the readiness probe.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.api.deps import (
    get_grocery_adapters,
    get_grocery_breakers,
    get_grocery_provider_registry,
)
from app.application.search_grocery_products import SearchGroceryProductsService
from app.core.config import GroceryProviderSetting, Settings, settings
from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery import GroceryProvider, GroceryProviderRegistry
from app.domain.grocery_catalog import GrocerySearchItem, GrocerySearchQuery
from app.grocery.circuit_breaker import BreakerPolicy, BreakerState, CircuitBreakerRegistry
from app.grocery.factory import build_grocery_adapter
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter
from app.grocery.resilient import CircuitBreakingGroceryAdapter

QUERY = GrocerySearchQuery(zip_code="06700", items=(GrocerySearchItem(ingredient="milk"),))


@pytest.fixture(autouse=True)
def _isolated_breakers():
    """Keep the process-wide breaker registry from leaking health state between tests."""
    get_grocery_breakers.cache_clear()
    yield
    get_grocery_breakers.cache_clear()


class _BrokenAdapter:
    """An adapter whose provider is down; counts calls so fail-fast can be asserted."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.calls = 0

    def search(self, query: GrocerySearchQuery):
        self.calls += 1
        raise GroceryProviderUnavailableError(self.provider_id, "upstream exploded")

    def place_order(self, request):  # pragma: no cover - not exercised by the search fan-out
        raise GroceryProviderUnavailableError(self.provider_id)

    def get_order_status(self, external_order_id):  # pragma: no cover - see above
        raise GroceryProviderUnavailableError(self.provider_id)


def _registry() -> GroceryProviderRegistry:
    return GroceryProviderRegistry(
        providers=(
            GroceryProvider(id="freshbasket", name="FreshBasket"),
            GroceryProvider(id="walmart", name="Walmart"),
        )
    )


# --- AC2: an open circuit falls back to the remaining providers --------------------------------


def test_a_failing_provider_is_skipped_while_the_healthy_ones_still_answer():
    breakers = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=2))
    broken = _BrokenAdapter("freshbasket")
    service = SearchGroceryProductsService(
        _registry(),
        {
            "freshbasket": CircuitBreakingGroceryAdapter(
                broken, breakers.for_provider("freshbasket")
            ),
            "walmart": CircuitBreakingGroceryAdapter(
                FakeGroceryProviderAdapter("walmart"), breakers.for_provider("walmart")
            ),
        },
    )

    assert [p.id for p in service.search(QUERY)] == ["walmart"]


def test_once_the_circuit_opens_the_broken_provider_is_no_longer_called():
    breakers = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=2))
    broken = _BrokenAdapter("freshbasket")
    service = SearchGroceryProductsService(
        _registry(),
        {
            "freshbasket": CircuitBreakingGroceryAdapter(
                broken, breakers.for_provider("freshbasket")
            ),
            "walmart": CircuitBreakingGroceryAdapter(
                FakeGroceryProviderAdapter("walmart"), breakers.for_provider("walmart")
            ),
        },
    )

    for _ in range(4):
        assert [p.id for p in service.search(QUERY)] == ["walmart"]

    assert broken.calls == 2  # the threshold; afterwards the breaker answers for it
    assert breakers.for_provider("freshbasket").state is BreakerState.OPEN
    assert breakers.for_provider("walmart").state is BreakerState.CLOSED


# --- composition root: breakers outlive the per-request adapters --------------------------------


def test_every_wired_adapter_is_wrapped_in_its_own_circuit_breaker():
    registry = get_grocery_provider_registry()
    adapters = get_grocery_adapters(registry, get_grocery_breakers())

    assert set(adapters) == {provider.id for provider in registry.available()}
    for provider_id, adapter in adapters.items():
        assert isinstance(adapter, CircuitBreakingGroceryAdapter)
        assert adapter.provider_id == provider_id
        assert adapter.breaker.snapshot().provider_id == provider_id


def test_breaker_state_survives_the_rebuilding_of_adapters_between_requests():
    registry = get_grocery_provider_registry()
    breakers = get_grocery_breakers()
    first = get_grocery_adapters(registry, breakers)
    second = get_grocery_adapters(registry, breakers)

    assert first["freshbasket"] is not second["freshbasket"]
    assert first["freshbasket"].breaker is second["freshbasket"].breaker


def test_the_breaker_registry_is_shared_process_wide():
    assert get_grocery_breakers() is get_grocery_breakers()


# --- AC1: per-provider timeouts ----------------------------------------------------------------


def test_a_provider_may_override_the_service_wide_request_timeout():
    settings = Settings(
        freshbasket_api_key=SecretStr("fb-sandbox-abc"),  # gitleaks:allow
        http_timeout_seconds=5.0,
        grocery_providers=(
            GroceryProviderSetting(id="freshbasket", name="FreshBasket", timeout_seconds=2.5),
        ),
    )

    adapter = build_grocery_adapter("freshbasket", settings=settings)

    assert isinstance(adapter, FreshBasketGroceryAdapter)
    assert adapter._timeout == 2.5


def test_a_provider_without_its_own_timeout_inherits_the_service_wide_one():
    settings = Settings(
        freshbasket_api_key=SecretStr("fb-sandbox-abc"),  # gitleaks:allow
        http_timeout_seconds=7.5,
        grocery_providers=(GroceryProviderSetting(id="freshbasket", name="FreshBasket"),),
    )

    adapter = build_grocery_adapter("freshbasket", settings=settings)

    assert adapter._timeout == 7.5


def test_one_providers_timeout_does_not_bleed_into_another():
    settings = Settings(
        walmart_api_key=SecretStr("wm-sandbox-abc"),  # gitleaks:allow
        http_timeout_seconds=5.0,
        grocery_providers=(
            GroceryProviderSetting(id="freshbasket", name="FreshBasket", timeout_seconds=1.5),
            GroceryProviderSetting(id="walmart", name="Walmart"),
        ),
    )

    adapter = build_grocery_adapter("walmart", settings=settings)

    assert adapter._timeout == 5.0


# --- AC3: breaker state is observable -----------------------------------------------------------


def test_readiness_reports_every_provider_circuit_as_closed_while_healthy(client):
    breakers = get_grocery_breakers()
    for provider_id in ("freshbasket", "walmart", "chedraui"):
        breakers.for_provider(provider_id)

    body = client.get("/health/ready").json()

    assert body["status"] == "ready"
    assert [entry["id"] for entry in body["groceryProviders"]] == [
        "chedraui",
        "freshbasket",
        "walmart",
    ]
    assert {entry["state"] for entry in body["groceryProviders"]} == {"closed"}


def test_readiness_reports_an_open_circuit_without_making_the_service_unready(client):
    breaker = get_grocery_breakers().for_provider("freshbasket")
    for _ in range(settings.grocery_breaker_failure_threshold):
        breaker.record_failure()
    assert breaker.state is BreakerState.OPEN

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ready"
    reported = next(e for e in body["groceryProviders"] if e["id"] == "freshbasket")
    assert reported["state"] == "open"
    assert reported["consecutiveFailures"] == settings.grocery_breaker_failure_threshold
    assert reported["secondsUntilRetry"] > 0


def test_a_search_that_trips_a_provider_shows_up_on_the_readiness_probe(client):
    breaker = get_grocery_breakers().for_provider("walmart")
    adapter = CircuitBreakingGroceryAdapter(_BrokenAdapter("walmart"), breaker)
    service = SearchGroceryProductsService(_registry(), {"walmart": adapter})

    for _ in range(settings.grocery_breaker_failure_threshold):
        assert service.search(QUERY) == ()
    assert breaker.state is BreakerState.OPEN

    reported = next(
        e for e in client.get("/health/ready").json()["groceryProviders"] if e["id"] == "walmart"
    )
    assert reported["state"] == "open"
