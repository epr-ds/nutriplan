"""COM-807: end-to-end commerce journey — plan → checkout → pay → track.

Drives the same journey a real client takes through the Commerce gateway edge
(``/commerce/v1``) — an order created from a meal plan is checked out, charged through a
payment method and then tracked — and asserts the composed state at each step.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_create_order_service, get_get_order_service, get_token_verifier
from app.application.create_order import CreateOrderService
from app.application.get_order import GetOrderService
from app.core.principal import Principal
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
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

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

MEAL_PLAN_ID = uuid.uuid4()

VALID_BODY = {
    "mealPlanId": str(MEAL_PLAN_ID),
    "fulfillmentType": "dark_kitchen",
    "deliveryAddress": {
        "street": "Av. Reforma 100",
        "city": "CDMX",
        "state": "CDMX",
        "zipCode": "06600",
        "country": "MX",
    },
    "deliveryDate": "2026-07-10",
    "deliveryTimeSlot": "12:00-13:00",
}

CARD_METHOD = {
    "type": "credit_card",
    "token": "tok_visa_secret",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=str(MEAL_PLAN_ID),
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None),
        ],
    )


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_create_order_service, None)
    app.dependency_overrides.pop(get_get_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build() -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    )
    app.dependency_overrides[get_get_order_service] = lambda: GetOrderService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_end_to_end_journey_plan_checkout_pay_track_is_coherent():
    client, repo = _build()

    checkout = client.post(
        "/commerce/v1/orders",
        json={**VALID_BODY, "paymentMethod": CARD_METHOD},
        headers=_auth(),
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()
    assert order["status"] == "confirmed"

    tracked = client.get(f"/commerce/v1/orders/{order['id']}", headers=_auth())
    assert tracked.status_code == 200, tracked.text
    assert tracked.json()["status"] == order["status"]
