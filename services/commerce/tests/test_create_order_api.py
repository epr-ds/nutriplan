"""COM-102 API tests for ``POST /orders`` (no DB, no network via dependency overrides).

The service is overridden with in-memory fakes and the token verifier with a stub, so the test
exercises the real router, request/response models, auth dependency, and domain-error mapping
without Postgres or a live Dietary.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_create_order_service, get_token_verifier
from app.application.create_order import CreateOrderService
from app.core.principal import Principal
from app.domain.errors import MealPlanUnavailableError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.main import app
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryOrderRepository,
    StubVerifier,
    make_test_pricer,
)

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

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


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=VALID_BODY["mealPlanId"],
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None),
        ],
    )


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_create_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(provider) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo, provider, make_test_pricer()
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_returns_201_with_projection():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))

    response = client.post("/orders", json=VALID_BODY, headers=_auth())

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["fulfillmentType"] == "dark_kitchen"
    assert data["provider"] is None
    assert [item["name"] for item in data["items"]] == ["Oatmeal Bowl", "Lunch"]
    assert data["items"][0]["unit"] == "serving"
    assert data["items"][0]["unitPrice"]["amount"] == 10.0
    assert data["items"][0]["lineTotal"]["amount"] == 10.0
    assert data["subtotal"]["amount"] == 50.0
    assert data["deliveryFee"]["amount"] == 35.0
    assert data["total"]["amount"] == 85.0
    assert data["total"]["currency"] == "MXN"
    assert uuid.UUID(data["id"])


def test_persists_order_scoped_to_caller():
    client, repo = _build(FakeMealPlanProvider(_snapshot()))

    client.post("/orders", json=VALID_BODY, headers=_auth())

    assert len(repo.orders) == 1
    order = next(iter(repo.orders.values()))
    assert order.user_id == uuid.UUID(PRINCIPAL.user_id)


def test_forwards_caller_token_to_provider():
    provider = FakeMealPlanProvider(_snapshot())
    client, _ = _build(provider)

    client.post("/orders", json=VALID_BODY, headers=_auth())

    assert provider.calls == [(VALID_BODY["mealPlanId"], GOOD_TOKEN)]


def test_requires_authentication():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))
    response = client.post("/orders", json=VALID_BODY)
    assert response.status_code == 401


def test_rejects_unknown_token():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))
    response = client.post("/orders", json=VALID_BODY, headers=_auth("nope"))
    assert response.status_code == 401


def test_missing_or_unowned_plan_returns_404():
    client, repo = _build(FakeMealPlanProvider(None))
    response = client.post("/orders", json=VALID_BODY, headers=_auth())
    assert response.status_code == 404
    assert repo.orders == {}


def test_grocery_delivery_without_provider_returns_422():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))
    body = {**VALID_BODY, "fulfillmentType": "grocery_delivery"}
    response = client.post("/orders", json=body, headers=_auth())
    assert response.status_code == 422


def test_grocery_delivery_with_provider_returns_201():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))
    body = {**VALID_BODY, "fulfillmentType": "grocery_delivery", "providerId": "freshbasket"}
    response = client.post("/orders", json=body, headers=_auth())
    assert response.status_code == 201
    data = response.json()
    assert data["fulfillmentType"] == "grocery_delivery"
    assert data["provider"]["id"] == "freshbasket"
    assert data["deliveryFee"]["amount"] == 49.0
    assert data["total"]["amount"] == 99.0


def test_malformed_body_returns_422():
    client, _ = _build(FakeMealPlanProvider(_snapshot()))
    body = {k: v for k, v in VALID_BODY.items() if k != "deliveryDate"}
    response = client.post("/orders", json=body, headers=_auth())
    assert response.status_code == 422


def test_dietary_unavailable_returns_503_problem_json():
    class _Unavailable:
        def fetch(self, plan_id: str, *, bearer_token: str):
            raise MealPlanUnavailableError("boom")

    client, _ = _build(_Unavailable())
    response = client.post("/orders", json=VALID_BODY, headers=_auth())
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["title"]
