"""COM-805: fulfillment resilience -- placement through the real circuit-breaker wiring.

Where ``test_grocery_resilience`` drives the cross-provider fan-out fallback and the readiness
probe, and ``test_grocery_order_placement`` drives the placer over a plain fake, this module closes
the QA gap the story leaves open: a *confirmed* grocery order has to be placed through the real
breaker wiring, so a provider whose circuit is already OPEN is refused (short-circuit, no network)
and the order is left unplaced rather than failing, and a provider *timeout* must be
normalised onto the domain error so it trips that same circuit, not leaking a transport exception
past the ACL.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.application.place_grocery_order import GroceryOrderPlacer
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery_catalog import GrocerySearchItem, GrocerySearchQuery
from app.domain.meal_plan import PlannedMeal
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.grocery.circuit_breaker import BreakerPolicy, BreakerState, CircuitBreakerRegistry
from app.grocery.resilient import CircuitBreakingGroceryAdapter
from tests.fakes import InMemoryOrderRepository, make_test_pricer

PROVIDER_ID = "freshbasket"


class _FailingAdapter:
    """An adapter whose every call fails, to prove the fallback and the circuit both engage."""

    def __init__(self, provider_id: str = PROVIDER_ID) -> None:
        self.provider_id = provider_id
        self.calls = 0

    def search(self, query):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise GroceryProviderUnavailableError(self.provider_id, "upstream exploded")

    def place_order(self, request):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise GroceryProviderUnavailableError(self.provider_id, "upstream exploded")

    def get_order_status(self, external_order_id):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise GroceryProviderUnavailableError(self.provider_id, "upstream exploded")


class _TimingOutAdapter:
    """A grocery adapter whose transport-level faults are raw provider failures (e.g. a timeout)."""

    def __init__(self, provider_id: str = PROVIDER_ID) -> None:
        self.provider_id = provider_id
        self.calls = 0

    def search(self, query):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise httpx.TimeoutException("provider timed out")

    def place_order(self, request):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise httpx.TimeoutException("provider timed out")

    def get_order_status(self, external_order_id):  # noqa: ANN001, ANN201 - test double
        self.calls += 1
        raise httpx.TimeoutException("provider timed out")


def _confirmed_grocery_order() -> Order:
    """A confirmed grocery order for Milk and Eggs, ready to be placed with its provider."""
    order = Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=Address(
            street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
        ),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=OrderStatus.CONFIRMED,
        provider_id=PROVIDER_ID,
    )
    pricer = make_test_pricer()
    for name, servings in (("Milk", "1"), ("Eggs", "2")):
        order.add_item(
            pricer.price_item(
                PlannedMeal(meal_type="breakfast", servings=Decimal(servings), recipe_name=name)
            )
        )
    return order


# --- AC1: a provider timeout becomes the domain error, tripping the circuit -------------


def test_a_provider_timeout_is_normalised_onto_the_domain_error_by_the_acl():
    breakers = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=1))
    timing_out = _TimingOutAdapter()
    adapter = CircuitBreakingGroceryAdapter(timing_out, breakers.for_provider(PROVIDER_ID))

    with pytest.raises(GroceryProviderUnavailableError):
        adapter.search(
            GrocerySearchQuery(zip_code="06600", items=(GrocerySearchItem(ingredient="milk"),))
        )

    assert adapter.breaker.state is BreakerState.OPEN
    assert adapter.breaker.snapshot().consecutive_failures == 1
    assert timing_out.calls == 1  # the normalised failure tripped the circuit


# --- AC2: an open circuit refuses placement and leaves the order unplaced ------------


def test_a_confirmed_order_is_refused_while_the_circuit_is_open():
    breakers = CircuitBreakerRegistry(policy=BreakerPolicy(failure_threshold=1))
    failing = _FailingAdapter()
    repo = InMemoryOrderRepository()
    adapter = CircuitBreakingGroceryAdapter(failing, breakers.for_provider(PROVIDER_ID))
    placer = GroceryOrderPlacer(repo, {PROVIDER_ID: adapter}, InMemoryEventPublisher())
    order = _confirmed_grocery_order()
    repo.add(order)

    # The first placement trips the circuit (the provider was failing).
    assert placer.place(order) is None
    assert failing.calls == 1
    assert adapter.breaker.state is BreakerState.OPEN

    # The next placement -- same confirmed order, still unplaced -- is refused by the open circuit,
    # short-circuits without touching the provider, and leaves the order unplaced (the fallback).
    assert placer.place(order) is None

    assert failing.calls == 1  # the open circuit refused the second placement: no network at all
    assert adapter.breaker.state is BreakerState.OPEN
    assert order.is_placed_with_provider is False
    assert order.status is OrderStatus.CONFIRMED
