"""COM-102/103 unit tests for :class:`CreateOrderService` (no DB, no network)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import MealPlanNotFoundError, OrderValidationError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from tests.fakes import FakeMealPlanProvider, InMemoryOrderRepository, make_test_pricer

USER_ID = uuid.uuid4()
PLAN_ID = str(uuid.uuid4())
TOKEN = "caller-token"


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _command(**overrides) -> CreateOrderCommand:
    base = dict(
        user_id=USER_ID,
        meal_plan_id=PLAN_ID,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id=None,
        notes=None,
    )
    base.update(overrides)
    return CreateOrderCommand(**base)


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None),
        ],
    )


def _service(
    snapshot: MealPlanSnapshot | None,
) -> tuple[CreateOrderService, InMemoryOrderRepository, FakeMealPlanProvider]:
    repo = InMemoryOrderRepository()
    provider = FakeMealPlanProvider(snapshot)
    return CreateOrderService(repo, provider, make_test_pricer()), repo, provider


def test_builds_items_from_plan_meals():
    service, repo, _ = _service(_snapshot())

    order = service.create(_command(), bearer_token=TOKEN)

    assert order.id in repo.orders
    assert order.status is OrderStatus.PENDING
    assert order.user_id == USER_ID
    assert [i.name for i in order.items] == ["Oatmeal Bowl", "Lunch"]
    assert [i.quantity for i in order.items] == [Decimal("1"), Decimal("2")]
    assert all(i.unit == "serving" for i in order.items)
    # Priced by make_test_pricer: breakfast 10.00, lunch 20.00 per serving.
    assert [i.unit_price.amount for i in order.items] == [Decimal("10.00"), Decimal("20.00")]
    assert [i.line_total.amount for i in order.items] == [Decimal("10.00"), Decimal("40.00")]


def test_computes_subtotal_delivery_fee_and_total():
    service, _, _ = _service(_snapshot())
    order = service.create(_command(), bearer_token=TOKEN)
    assert order.subtotal.amount == Decimal("50.00")  # 10 + 40
    assert order.delivery_fee.amount == Decimal("35.00")  # dark_kitchen
    assert order.total.amount == Decimal("85.00")


def test_forwards_bearer_token_and_plan_id_to_provider():
    service, _, provider = _service(_snapshot())
    service.create(_command(), bearer_token=TOKEN)
    assert provider.calls == [(PLAN_ID, TOKEN)]


def test_missing_or_unowned_plan_raises_not_found():
    service, repo, _ = _service(None)
    with pytest.raises(MealPlanNotFoundError):
        service.create(_command(), bearer_token=TOKEN)
    assert repo.orders == {}


def test_grocery_delivery_without_provider_is_rejected_before_fetch():
    service, _, provider = _service(_snapshot())
    with pytest.raises(OrderValidationError):
        service.create(
            _command(fulfillment_type=FulfillmentType.GROCERY_DELIVERY, provider_id=None),
            bearer_token=TOKEN,
        )
    assert provider.calls == []


def test_grocery_delivery_with_provider_is_accepted():
    service, _, _ = _service(_snapshot())
    order = service.create(
        _command(fulfillment_type=FulfillmentType.GROCERY_DELIVERY, provider_id="freshbasket"),
        bearer_token=TOKEN,
    )
    assert order.fulfillment_type is FulfillmentType.GROCERY_DELIVERY
    assert order.provider_id == "freshbasket"
    assert order.delivery_fee.amount == Decimal("49.00")  # grocery_delivery
    assert order.total.amount == Decimal("99.00")  # 50 subtotal + 49


def test_empty_plan_produces_order_with_no_items():
    service, _, _ = _service(MealPlanSnapshot(plan_id=PLAN_ID, meals=[]))
    order = service.create(_command(), bearer_token=TOKEN)
    assert order.items == []
    assert order.subtotal.amount == Decimal("0.00")
    assert order.total.amount == Decimal("35.00")  # dark_kitchen fee still applies
