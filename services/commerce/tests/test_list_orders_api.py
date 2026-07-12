"""COM-104 API tests for ``GET /orders`` (no DB, no network via dependency overrides).

The list service is overridden with a faithful in-memory repository and the token verifier with a
stub, so the tests exercise the real router, query-param validation, auth dependency, and array
projection without Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_list_orders_service, get_token_verifier
from app.application.list_orders import ListOrdersService
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
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _order(
    *,
    created_at: datetime = BASE,
    status: OrderStatus = OrderStatus.PENDING,
    user_id: uuid.UUID = USER,
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
        created_at=created_at,
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
    app.dependency_overrides.pop(get_list_orders_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*orders: Order) -> TestClient:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    app.dependency_overrides[get_list_orders_service] = lambda: ListOrdersService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_returns_200_array_projection():
    order = _order(with_item=True, provider_id="prov-1")
    client = _build(order)

    response = client.get("/orders", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == str(order.id)
    assert data[0]["status"] == "pending"
    assert data[0]["items"][0]["name"] == "Protein Bowl"
    assert data[0]["items"][0]["unitPrice"]["amount"] == 50.0
    assert data[0]["provider"]["id"] == "prov-1"


def test_orders_returned_newest_first():
    older = _order(created_at=BASE)
    newer = _order(created_at=BASE + timedelta(hours=1))
    client = _build(older, newer)

    data = client.get("/orders", headers=_auth()).json()

    assert [row["id"] for row in data] == [str(newer.id), str(older.id)]


def test_scoped_to_caller():
    mine = _order(created_at=BASE)
    theirs = _order(created_at=BASE, user_id=uuid.uuid4())
    client = _build(mine, theirs)

    data = client.get("/orders", headers=_auth()).json()

    assert [row["id"] for row in data] == [str(mine.id)]


def test_requires_authentication():
    client = _build(_order())
    assert client.get("/orders").status_code == 401


def test_rejects_unknown_token():
    client = _build(_order())
    assert client.get("/orders", headers=_auth("nope")).status_code == 401


def test_filters_by_status_query():
    pending = _order(created_at=BASE, status=OrderStatus.PENDING)
    delivered = _order(created_at=BASE, status=OrderStatus.DELIVERED)
    client = _build(pending, delivered)

    data = client.get("/orders", params={"status": "delivered"}, headers=_auth()).json()

    assert [row["id"] for row in data] == [str(delivered.id)]


def test_filters_by_from_date_query():
    old = _order(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    recent = _order(created_at=datetime(2026, 6, 1, tzinfo=UTC))
    client = _build(old, recent)

    data = client.get("/orders", params={"fromDate": "2026-03-01"}, headers=_auth()).json()

    assert [row["id"] for row in data] == [str(recent.id)]


def test_paginates_with_page_and_limit():
    orders = [_order(created_at=BASE + timedelta(hours=i)) for i in range(3)]
    client = _build(*orders)
    newest_first = [str(orders[2].id), str(orders[1].id), str(orders[0].id)]

    page1 = client.get("/orders", params={"page": 1, "limit": 2}, headers=_auth()).json()
    page2 = client.get("/orders", params={"page": 2, "limit": 2}, headers=_auth()).json()

    assert [row["id"] for row in page1] == newest_first[:2]
    assert [row["id"] for row in page2] == newest_first[2:]


def test_empty_list_when_no_orders():
    client = _build()
    response = client.get("/orders", headers=_auth())
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"limit": 0},
        {"limit": 101},
        {"status": "not_a_status"},
    ],
)
def test_invalid_query_params_return_422(params: dict[str, object]):
    client = _build(_order())
    assert client.get("/orders", params=params, headers=_auth()).status_code == 422
