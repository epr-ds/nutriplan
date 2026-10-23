"""COM-605: price an order for a meal plan without placing it (``POST /orders/quote``).

The quote uses the same pricer as order creation, so the checkout's review shows exactly what the
order will cost. Covered at three levels: the pricer, the use case (plan lookup, validation) and
the HTTP edge (auth, validation, error mapping), with Dietary and the token check replaced by fakes.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quote_order_service, get_token_verifier
from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.application.queries import QuoteOrderQuery
from app.application.quote_order import QuoteOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType
from app.domain.errors import MealPlanNotFoundError, MealPlanUnavailableError, OrderValidationError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.money import Money
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    StubVerifier,
    make_test_pricer,
)

TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
PLAN_ID = str(uuid.uuid4())


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="dinner", servings=Decimal("2"), recipe_name="Lentil soup"),
        ],
    )


class _UnavailableMealPlans:
    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None:
        raise MealPlanUnavailableError("Dietary is down")


# --- the pricer -----------------------------------------------------------------------------------


def test_a_quote_prices_each_meal_and_adds_the_delivery_fee():
    quote = make_test_pricer().quote(_snapshot().meals, FulfillmentType.DARK_KITCHEN)

    assert [item.name for item in quote.items] == ["Oatmeal Bowl", "Lentil soup"]
    totals = [item.line_total for item in quote.items]
    assert totals == [Money(Decimal("10.00")), Money(Decimal("60.00"))]
    assert quote.subtotal == Money(Decimal("70.00"))
    assert quote.delivery_fee == Money(Decimal("35.00"))
    assert quote.total == Money(Decimal("105.00"))


def test_pickup_has_no_delivery_fee():
    quote = make_test_pricer().quote(_snapshot().meals, FulfillmentType.PICKUP)

    assert quote.delivery_fee == Money(Decimal("0.00"))
    assert quote.total == quote.subtotal


# --- the use case -------------------------------------------------------------------------------


def _service(provider=None) -> QuoteOrderService:
    return QuoteOrderService(provider or FakeMealPlanProvider(_snapshot()), make_test_pricer())


def test_the_quote_reads_the_plan_with_the_callers_token():
    provider = FakeMealPlanProvider(_snapshot())

    _service(provider).quote(
        QuoteOrderQuery(meal_plan_id=PLAN_ID, fulfillment_type=FulfillmentType.PICKUP),
        bearer_token=TOKEN,
    )

    assert provider.calls == [(PLAN_ID, TOKEN)]


def test_a_grocery_quote_needs_a_provider():
    with pytest.raises(OrderValidationError):
        _service().quote(
            QuoteOrderQuery(
                meal_plan_id=PLAN_ID,
                fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
            ),
            bearer_token=TOKEN,
        )


def test_an_unknown_plan_cannot_be_quoted():
    with pytest.raises(MealPlanNotFoundError):
        _service(FakeMealPlanProvider(None)).quote(
            QuoteOrderQuery(meal_plan_id=PLAN_ID, fulfillment_type=FulfillmentType.PICKUP),
            bearer_token=TOKEN,
        )


def test_the_quote_matches_the_order_then_placed():
    query = QuoteOrderQuery(
        meal_plan_id=PLAN_ID,
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        provider_id="freshbasket",
    )
    quote = _service().quote(query, bearer_token=TOKEN)

    address = Address(street="s", city="c", state="st", zip_code="06600", country="MX")
    order = CreateOrderService(
        InMemoryOrderRepository(),
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    ).create(
        CreateOrderCommand(
            user_id=uuid.UUID(PRINCIPAL.user_id),
            meal_plan_id=PLAN_ID,
            fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
            delivery_address=address,
            delivery_date=date(2026, 11, 2),
            delivery_time_slot="13:00-15:00",
            provider_id="freshbasket",
        ),
        bearer_token=TOKEN,
    )

    assert [item.line_total for item in quote.items] == [item.line_total for item in order.items]
    assert quote.subtotal == order.subtotal
    assert (quote.delivery_fee, quote.total) == (order.delivery_fee, order.total)


# --- the HTTP edge ------------------------------------------------------------------------------


@pytest.fixture
def api():
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({TOKEN: PRINCIPAL})
    yield lambda provider=None: _bind(provider)
    app.dependency_overrides.pop(get_token_verifier, None)
    app.dependency_overrides.pop(get_quote_order_service, None)


def _bind(provider) -> TestClient:
    app.dependency_overrides[get_quote_order_service] = lambda: _service(provider)
    return TestClient(app)


_AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_api_returns_the_itemized_price(api):
    response = api().post(
        "/orders/quote",
        json={"mealPlanId": PLAN_ID, "fulfillmentType": "dark_kitchen"},
        headers=_AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Oatmeal Bowl", "Lentil soup"]
    assert body["items"][1]["unitPrice"]["amount"] == 30.0
    assert body["items"][1]["lineTotal"]["amount"] == 60.0
    assert body["subtotal"]["amount"] == 70.0
    assert body["deliveryFee"]["amount"] == 35.0
    assert body["total"]["amount"] == 105.0
    assert body["total"]["currency"] == "MXN"


def test_api_requires_a_token(api):
    response = api().post(
        "/orders/quote", json={"mealPlanId": PLAN_ID, "fulfillmentType": "pickup"}
    )

    assert response.status_code == 401


def test_api_grocery_without_provider_is_422(api):
    response = api().post(
        "/orders/quote",
        json={"mealPlanId": PLAN_ID, "fulfillmentType": "grocery_delivery"},
        headers=_AUTH,
    )

    assert response.status_code == 422


def test_api_rejects_an_unknown_fulfillment_type(api):
    response = api().post(
        "/orders/quote",
        json={"mealPlanId": PLAN_ID, "fulfillmentType": "drone"},
        headers=_AUTH,
    )

    assert response.status_code == 422


def test_api_unknown_plan_is_404(api):
    response = api(FakeMealPlanProvider(None)).post(
        "/orders/quote",
        json={"mealPlanId": PLAN_ID, "fulfillmentType": "pickup"},
        headers=_AUTH,
    )

    assert response.status_code == 404


def test_api_dietary_unavailable_is_503(api):
    response = api(_UnavailableMealPlans()).post(
        "/orders/quote",
        json={"mealPlanId": PLAN_ID, "fulfillmentType": "pickup"},
        headers=_AUTH,
    )

    assert response.status_code == 503
