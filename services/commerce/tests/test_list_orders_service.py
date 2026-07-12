"""COM-104 unit tests for :class:`ListOrdersService` (no DB, no network).

Exercises caller-scoping, status/date filters, newest-first ordering, and page/limit pagination
against the faithful in-memory repository fake.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.application.list_orders import ListOrdersService
from app.application.queries import ListOrdersQuery
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.order import Order
from tests.fakes import InMemoryOrderRepository

USER = uuid.uuid4()
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _order(
    user_id: uuid.UUID = USER,
    *,
    created_at: datetime,
    status: OrderStatus = OrderStatus.PENDING,
) -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
        created_at=created_at,
    )


def _service(*orders: Order) -> tuple[ListOrdersService, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    return ListOrdersService(repo), repo


def test_offset_derived_from_page_and_limit():
    assert ListOrdersQuery(user_id=USER, page=1, limit=20).offset == 0
    assert ListOrdersQuery(user_id=USER, page=2, limit=20).offset == 20
    assert ListOrdersQuery(user_id=USER, page=3, limit=15).offset == 30


def test_lists_only_callers_orders():
    other = uuid.uuid4()
    service, _ = _service(
        _order(created_at=BASE),
        _order(user_id=other, created_at=BASE),
    )

    result = service.list(ListOrdersQuery(user_id=USER))

    assert len(result) == 1
    assert result[0].user_id == USER


def test_orders_are_newest_first():
    older = _order(created_at=BASE)
    newer = _order(created_at=BASE + timedelta(hours=1))
    service, _ = _service(older, newer)

    result = service.list(ListOrdersQuery(user_id=USER))

    assert [o.id for o in result] == [newer.id, older.id]


def test_filters_by_status():
    pending = _order(created_at=BASE, status=OrderStatus.PENDING)
    delivered = _order(created_at=BASE, status=OrderStatus.DELIVERED)
    service, _ = _service(pending, delivered)

    result = service.list(ListOrdersQuery(user_id=USER, status=OrderStatus.DELIVERED))

    assert [o.id for o in result] == [delivered.id]


def test_filters_by_from_date():
    old = _order(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    recent = _order(created_at=datetime(2026, 6, 1, tzinfo=UTC))
    service, _ = _service(old, recent)

    result = service.list(ListOrdersQuery(user_id=USER, from_date=date(2026, 3, 1)))

    assert [o.id for o in result] == [recent.id]


def test_paginates_with_page_and_limit():
    orders = [_order(created_at=BASE + timedelta(hours=i)) for i in range(3)]
    service, _ = _service(*orders)
    newest_first = [orders[2].id, orders[1].id, orders[0].id]

    page1 = service.list(ListOrdersQuery(user_id=USER, page=1, limit=2))
    page2 = service.list(ListOrdersQuery(user_id=USER, page=2, limit=2))

    assert [o.id for o in page1] == newest_first[:2]
    assert [o.id for o in page2] == newest_first[2:]


def test_empty_when_user_has_no_orders():
    service, _ = _service()
    assert service.list(ListOrdersQuery(user_id=USER)) == []
