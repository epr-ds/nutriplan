"""COM-105 API tests for ``GET /orders/{orderId}`` (no DB, no network via dependency overrides).

The get service is overridden with a faithful in-memory repository and the token verifier with a
stub, so the tests exercise the real router, path-param validation, auth dependency, owner-scoped
404 (no enumeration), and the full ``OrderResponse`` projection without Postgres.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_get_order_service, get_token_verifier
from app.application.get_order import GetOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem
from app.main import app
from tests.fakes import InMemoryOrderRepository, StubVerifier

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)


def _order(
    *,
    user_id: uuid.UUID = USER,
    status: OrderStatus = OrderStatus.PENDING,
    with_item: bool = False,
    provider_id: str | None = None,
) -> Order:
    order = Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
        provider_id=provider_id,
    )
    if with_item:
        order.add_item(
            OrderItem(
                name="Protein Bowl",
                quantity=Decimal("2"),
                unit="serving",
                unit_price=Money(Decimal("50.00")),
                line_total=Money(Decimal("100.00")),
            )
        )
    return order


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_get_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*orders: Order) -> TestClient:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    app.dependency_overrides[get_get_order_service] = lambda: GetOrderService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_returns_200_full_projection():
    order = _order(with_item=True, provider_id="prov-1")
    client = _build(order)

    response = client.get(f"/orders/{order.id}", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(order.id)
    assert data["status"] == "pending"
    assert data["fulfillmentType"] == "dark_kitchen"
    assert data["items"][0]["name"] == "Protein Bowl"
    assert data["items"][0]["unitPrice"]["amount"] == 50.0
    assert data["items"][0]["lineTotal"]["amount"] == 100.0
    assert data["provider"]["id"] == "prov-1"
    # AC: returns the *full* OrderResponse — every documented top-level field is present.
    assert {"id", "status", "fulfillmentType", "items", "subtotal", "deliveryFee", "total"} <= set(
        data
    )


def test_unknown_id_returns_404():
    client = _build(_order())

    response = client.get(f"/orders/{uuid.uuid4()}", headers=_auth())

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_other_users_order_returns_404_no_enumeration():
    theirs = _order(user_id=uuid.uuid4())
    client = _build(theirs)

    # The order exists but is not owned by the caller: must be indistinguishable from unknown.
    response = client.get(f"/orders/{theirs.id}", headers=_auth())

    assert response.status_code == 404


def test_requires_authentication():
    order = _order()
    client = _build(order)

    assert client.get(f"/orders/{order.id}").status_code == 401


def test_rejects_unknown_token():
    order = _order()
    client = _build(order)

    assert client.get(f"/orders/{order.id}", headers=_auth("nope")).status_code == 401


def test_malformed_order_id_returns_422():
    client = _build(_order())

    assert client.get("/orders/not-a-uuid", headers=_auth()).status_code == 422
