"""COM-108 API tests for the RFC 7807 ``application/problem+json`` error model.

Every 4xx/5xx response from the Commerce API must be a problem document with a single, predictable
shape (``type``/``title``/``status`` plus an ``instance``). These tests exercise the real routers,
the auth dependency and owner scoping (Postgres-free via dependency overrides) and assert the
*transport* contract of errors:

* unauthenticated / invalid-token       -> 401 problem+json (+ ``WWW-Authenticate: Bearer``)
* a missing **or** cross-user order      -> 404 problem+json, indistinguishable (no ownership leak)
* an illegal lifecycle transition        -> 409 problem+json
* a domain precondition failure          -> 422 problem+json
* request/query validation failure       -> 422 problem+json carrying an ``errors`` array
* success responses stay ``application/json`` (the problem media type is errors-only)

The ``type`` member is asserted to be ``about:blank`` — the platform-wide RFC 7807 convention shared
by every NutriPlan service (identity/dietary/ai/commerce).
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
from app.payments.fake import FakePaymentProvider
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
MISSING_ID = "00000000-0000-0000-0000-000000000000"

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
        meals=[PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal")],
    )


def _order(*, user_id: uuid.UUID = USER, status: OrderStatus = OrderStatus.PENDING) -> Order:
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


def _build(*orders: Order) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    provider = FakeMealPlanProvider(_snapshot())
    publisher = InMemoryEventPublisher()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo, provider, make_test_pricer(), publisher, FakePaymentProvider()
    )
    app.dependency_overrides[get_list_orders_service] = lambda: ListOrdersService(repo)
    app.dependency_overrides[get_get_order_service] = lambda: GetOrderService(repo)
    app.dependency_overrides[get_cancel_order_service] = lambda: CancelOrderService(repo, publisher)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_problem(response, status_code: int, title: str) -> dict:
    assert response.status_code == status_code
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == title
    assert body["status"] == status_code
    return body


# --- 401 --------------------------------------------------------------------


def test_unauthenticated_request_returns_problem_json():
    order = _order()
    client, _ = _build(order)

    response = client.get(f"/orders/{order.id}")

    body = _assert_problem(response, 401, "Unauthorized")
    assert body["instance"] == f"/orders/{order.id}"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_invalid_token_returns_problem_json():
    order = _order()
    client, _ = _build(order)

    response = client.get(f"/orders/{order.id}", headers=_auth("bogus"))

    _assert_problem(response, 401, "Unauthorized")
    assert response.headers.get("www-authenticate") == "Bearer"


# --- 404 (missing and cross-user are indistinguishable) ---------------------


def test_missing_order_returns_404_problem_json():
    client, _ = _build()

    response = client.get(f"/orders/{MISSING_ID}", headers=_auth())

    body = _assert_problem(response, 404, "Not Found")
    assert body["instance"] == f"/orders/{MISSING_ID}"


def test_cross_user_order_returns_404_problem_json_without_leak():
    # An order that exists but belongs to someone else must look exactly like a missing one.
    theirs = _order(user_id=uuid.uuid4())
    client, _ = _build(theirs)

    missing = client.get(f"/orders/{MISSING_ID}", headers=_auth())
    unowned = client.get(f"/orders/{theirs.id}", headers=_auth())

    _assert_problem(missing, 404, "Not Found")
    unowned_body = _assert_problem(unowned, 404, "Not Found")
    # No ownership/existence leak: same status, same title, and the detail never says "forbidden".
    assert "forbidden" not in unowned_body.get("detail", "").lower()
    assert str(theirs.user_id) not in unowned_body.get("detail", "")


# --- 409 / 422 (domain) -----------------------------------------------------


def test_illegal_transition_returns_409_problem_json():
    order = _order(status=OrderStatus.IN_TRANSIT)
    client, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", headers=_auth())

    _assert_problem(response, 409, "Conflict")


def test_domain_precondition_returns_422_problem_json():
    # grocery_delivery without a providerId is a domain precondition failure (not a schema error).
    client, _ = _build()
    body = {**VALID_BODY, "fulfillmentType": "grocery_delivery"}

    response = client.post("/orders", json=body, headers=_auth())

    _assert_problem(response, 422, "Unprocessable Entity")


# --- 422 (request/query validation, with errors[] extension) ----------------


def test_request_validation_returns_422_problem_json_with_errors():
    client, _ = _build()
    body = {k: v for k, v in VALID_BODY.items() if k != "deliveryDate"}

    response = client.post("/orders", json=body, headers=_auth())

    body_out = _assert_problem(response, 422, "Unprocessable Entity")
    assert body_out["detail"] == "Request validation failed"
    assert isinstance(body_out["errors"], list) and body_out["errors"]
    first = body_out["errors"][0]
    assert {"loc", "msg", "type"} <= set(first)


def test_query_validation_returns_422_problem_json():
    # status is constrained to a known enum; an unknown value is a query-validation failure.
    client, _ = _build()

    response = client.get("/orders", params={"status": "teleported"}, headers=_auth())

    body_out = _assert_problem(response, 422, "Unprocessable Entity")
    assert isinstance(body_out["errors"], list) and body_out["errors"]


# --- success stays application/json -----------------------------------------


def test_success_response_is_plain_json():
    order = _order()
    client, _ = _build(order)

    response = client.get(f"/orders/{order.id}", headers=_auth())

    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0].strip() == "application/json"
