"""COM-105 unit tests for :class:`GetOrderService` (no DB, no network).

Exercises the owner-scoped read: the caller gets their own order back, while an unknown id and
another user's order are indistinguishable — both raise :class:`OrderNotFoundError` (no
enumeration) — against the faithful in-memory repository fake.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.application.get_order import GetOrderService
from app.application.queries import GetOrderQuery
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import OrderNotFoundError
from app.domain.order import Order
from tests.fakes import InMemoryOrderRepository

USER = uuid.uuid4()
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _order(user_id: uuid.UUID = USER, *, status: OrderStatus = OrderStatus.PENDING) -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
        created_at=BASE,
    )


def _service(*orders: Order) -> GetOrderService:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    return GetOrderService(repo)


def test_returns_callers_order():
    order = _order()
    service = _service(order)

    result = service.get(GetOrderQuery(user_id=USER, order_id=order.id))

    assert result.id == order.id
    assert result.user_id == USER


def test_unknown_id_raises_not_found():
    service = _service(_order())

    with pytest.raises(OrderNotFoundError):
        service.get(GetOrderQuery(user_id=USER, order_id=uuid.uuid4()))


def test_other_users_order_raises_not_found():
    other = uuid.uuid4()
    theirs = _order(user_id=other)
    service = _service(theirs)

    # The order exists, but not for this caller: indistinguishable from unknown (no enumeration).
    with pytest.raises(OrderNotFoundError):
        service.get(GetOrderQuery(user_id=USER, order_id=theirs.id))


def test_not_found_error_carries_the_requested_id():
    service = _service()
    missing = uuid.uuid4()

    with pytest.raises(OrderNotFoundError) as exc_info:
        service.get(GetOrderQuery(user_id=USER, order_id=missing))

    assert exc_info.value.order_id == missing
