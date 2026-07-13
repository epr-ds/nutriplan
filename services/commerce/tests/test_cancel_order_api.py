"""COM-107 API tests for ``POST /orders/{orderId}/cancel`` (no DB, no network via overrides).

The cancel service is overridden with a faithful in-memory repository and the token verifier with a
stub, so the tests exercise the real router, path-param validation, the auth dependency, the
owner-scoped ``404`` (no enumeration), the state-machine ``409`` guard, and the ``OrderResponse``
projection — all without Postgres.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cancel_order_service, get_get_order_service, get_token_verifier
from app.application.cancel_order import CancelOrderService
from app.application.get_order import GetOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.main import app
from tests.fakes import InMemoryOrderRepository, StubVerifier

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)


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
    app.dependency_overrides.pop(get_cancel_order_service, None)
    app.dependency_overrides.pop(get_get_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*orders: Order) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    app.dependency_overrides[get_cancel_order_service] = lambda: CancelOrderService(
        repo, InMemoryEventPublisher()
    )
    app.dependency_overrides[get_get_order_service] = lambda: GetOrderService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING]
)
def test_cancel_returns_200_cancelled(status: OrderStatus):
    order = _order(status=status)
    client, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", headers=_auth())

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_persists_status():
    order = _order(status=OrderStatus.CONFIRMED)
    client, _ = _build(order)

    assert client.post(f"/orders/{order.id}/cancel", headers=_auth()).status_code == 200
    # A subsequent read reflects the cancellation (persisted via the shared repository).
    got = client.get(f"/orders/{order.id}", headers=_auth())
    assert got.status_code == 200
    assert got.json()["status"] == "cancelled"


@pytest.mark.parametrize(
    "status", [OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED, OrderStatus.CANCELLED]
)
def test_cancel_after_dispatch_returns_409(status: OrderStatus):
    order = _order(status=status)
    client, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", headers=_auth())

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_id_returns_404():
    client, _ = _build(_order())

    response = client.post(f"/orders/{uuid.uuid4()}/cancel", headers=_auth())

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_other_users_order_returns_404_no_enumeration():
    theirs = _order(user_id=uuid.uuid4())
    client, repo = _build(theirs)

    # The order exists but is not owned by the caller: must be indistinguishable from unknown.
    response = client.post(f"/orders/{theirs.id}/cancel", headers=_auth())

    assert response.status_code == 404
    # And it must be left untouched for its real owner.
    assert repo.orders[theirs.id].status is OrderStatus.PENDING


def test_requires_authentication():
    order = _order()
    client, _ = _build(order)

    assert client.post(f"/orders/{order.id}/cancel").status_code == 401


def test_rejects_unknown_token():
    order = _order()
    client, _ = _build(order)

    assert client.post(f"/orders/{order.id}/cancel", headers=_auth("nope")).status_code == 401


def test_malformed_order_id_returns_422():
    client, _ = _build(_order())

    assert client.post("/orders/not-a-uuid/cancel", headers=_auth()).status_code == 422
