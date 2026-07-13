"""COM-108 ownership-guard lock-in tests spanning *every* order route.

The ownership guarantee is that every ``/orders`` route is scoped to the JWT subject: it requires a
valid bearer token, and it never lets one user observe or mutate another user's order. That guard is
implemented incrementally (a required ``CurrentPrincipal`` dependency + an owner-scoped repository),
so this suite pins it down across the whole surface at once — a future route that forgets to scope
itself, or drops the auth dependency, fails here.

Postgres-free: services use an in-memory repository and a stub verifier (dependency overrides).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_cancel_order_service,
    get_create_order_service,
    get_get_order_service,
    get_list_orders_service,
    get_token_verifier,
)
from app.application.cancel_order import CancelOrderService
from app.application.create_order import CreateOrderService
from app.application.get_order import GetOrderService
from app.application.list_orders import ListOrdersService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.main import app
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryOrderRepository,
    StubVerifier,
    make_test_pricer,
)

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)
OTHER = uuid.uuid4()


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=str(uuid.uuid4()),
        meals=[PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal")],
    )


def _order(*, user_id: uuid.UUID, status: OrderStatus = OrderStatus.PENDING) -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
    )


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    for dep in (
        get_create_order_service,
        get_list_orders_service,
        get_get_order_service,
        get_cancel_order_service,
        get_token_verifier,
    ):
        app.dependency_overrides.pop(dep, None)


def _build(
    *orders: Order, plan_available: bool = True
) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    # An unavailable plan (provider returns None) models "not one of the caller's plans" for the
    # create route — Dietary reports a missing/not-owned plan as 404 (no enumeration).
    provider = FakeMealPlanProvider(_snapshot() if plan_available else None)
    publisher = InMemoryEventPublisher()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo, provider, make_test_pricer(), publisher
    )
    app.dependency_overrides[get_list_orders_service] = lambda: ListOrdersService(repo)
    app.dependency_overrides[get_get_order_service] = lambda: GetOrderService(repo)
    app.dependency_overrides[get_cancel_order_service] = lambda: CancelOrderService(repo, publisher)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Every order route, as (method, path-template). ``{}`` is filled with a concrete order id per test.
_ROUTES = [
    ("POST", "/orders"),
    ("GET", "/orders"),
    ("GET", "/orders/{}"),
    ("POST", "/orders/{}/cancel"),
]


@pytest.mark.parametrize("method,template", _ROUTES)
def test_every_order_route_requires_authentication(method: str, template: str):
    client, _ = _build()
    path = template.format(uuid.uuid4())

    response = client.request(method, path)

    assert response.status_code == 401
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("method,template", _ROUTES)
def test_every_order_route_rejects_unknown_token(method: str, template: str):
    client, _ = _build()
    path = template.format(uuid.uuid4())

    response = client.request(method, path, headers=_auth("nope"))

    assert response.status_code == 401


def test_get_of_another_users_order_is_404():
    theirs = _order(user_id=OTHER)
    client, _ = _build(theirs)

    assert client.get(f"/orders/{theirs.id}", headers=_auth()).status_code == 404


def test_cancel_of_another_users_order_is_404_and_leaves_it_untouched():
    theirs = _order(user_id=OTHER, status=OrderStatus.PENDING)
    client, repo = _build(theirs)

    assert client.post(f"/orders/{theirs.id}/cancel", headers=_auth()).status_code == 404
    # The real owner's order is not mutated by a stranger's cancel attempt.
    assert repo.orders[theirs.id].status is OrderStatus.PENDING


def test_list_returns_only_the_callers_orders():
    mine_a = _order(user_id=USER)
    mine_b = _order(user_id=USER)
    theirs = _order(user_id=OTHER)
    client, _ = _build(mine_a, mine_b, theirs)

    response = client.get("/orders", headers=_auth())

    assert response.status_code == 200
    returned = {item["id"] for item in response.json()}
    assert returned == {str(mine_a.id), str(mine_b.id)}
    assert str(theirs.id) not in returned


def test_create_against_an_unowned_plan_is_404_and_persists_nothing():
    client, repo = _build(plan_available=False)
    body = {
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

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 404
    assert repo.orders == {}
