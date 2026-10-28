"""COM-809: automated payment security regressions — no PAN, tokenization boundaries.

Where the payment flows were proven end to end (COM-804, COM-202/203/204/205/206), the security half
of the story still needs its own regression suite: a raw card number must never be accepted as a
payment token at the gateway boundary, must never reach persisted order/charge state, and must
never travel through an error or log line.

These tests pin the boundary through the HTTP surface (``/commerce/v1``) with the same in-process
fakes and stub verifier the happy-path suites use, so an insecure acceptance is caught before it
ever reaches a real provider.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_create_order_service, get_payment_method_service, get_token_verifier
from app.application.create_order import CreateOrderService
from app.application.payment_methods import PaymentMethodService
from app.core.principal import Principal
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    InMemoryPaymentMethodRepository,
    StubVerifier,
    make_test_pricer,
)

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)

# A Luhn-valid raw card number: the kind of value that must be rejected as a payment token.
PAN = "4111111111111111"

_CARD_BODY: dict[str, Any] = {
    "type": "credit_card",
    "token": "tok_visa_secret",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_create_order_service, None)
    app.dependency_overrides.pop(get_payment_method_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _snapshot() -> Any:
    from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal

    return MealPlanSnapshot(
        plan_id=str(uuid.uuid4()),
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
        ],
    )


VALID_BODY = {
    "mealPlanId": str(uuid.uuid4()),
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


@pytest.fixture
def methods_client() -> tuple[TestClient, InMemoryPaymentMethodRepository]:
    repo = InMemoryPaymentMethodRepository()
    app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.pop(get_payment_method_service, None)
        app.dependency_overrides.pop(get_token_verifier, None)


def test_gateway_rejects_a_raw_pan_as_a_saved_payment_method_token(methods_client) -> None:
    """A raw card number must never be storable as a payment token (COM-809)."""

    api_client, repo = methods_client
    response = api_client.post(
        "/commerce/v1/payment-methods",
        json={**_CARD_BODY, "token": PAN},
        headers=_auth(),
    )
    assert response.status_code == 422
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON
    assert len(repo.list_for_user(USER)) == 0


def test_gateway_rejects_a_raw_pan_as_an_order_charge_token() -> None:
    """A raw card number must never be chargeable through an order (COM-809)."""

    repo = InMemoryOrderRepository()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    client = TestClient(app)
    response = client.post(
        "/commerce/v1/orders",
        json={
            **VALID_BODY,
            "mealPlanId": str(uuid.uuid4()),
            "paymentMethod": {**_CARD_BODY, "token": PAN},
        },
        headers=_auth(),
    )
    assert response.status_code == 422
    assert len(repo.orders) == 0
