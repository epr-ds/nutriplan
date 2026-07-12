"""COM-107 unit tests for :class:`CancelOrderService` (no DB, no network).

Exercises the owner-scoped cancel: the caller can cancel their own order while it is still
pre-dispatch (pending/confirmed/preparing); an unknown id and another user's order are
indistinguishable (both :class:`OrderNotFoundError`, no enumeration); and once the order has been
dispatched or reached a terminal state the domain refuses with
:class:`IllegalOrderTransitionError`. All run against the faithful in-memory repository fake.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.application.cancel_order import CancelOrderService
from app.application.commands import CancelOrderCommand
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import IllegalOrderTransitionError, OrderNotFoundError
from app.domain.order import Order
from tests.fakes import InMemoryOrderRepository

USER = uuid.uuid4()


def _order(user_id: uuid.UUID = USER, *, status: OrderStatus = OrderStatus.PENDING) -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
    )


def _service(*orders: Order) -> tuple[CancelOrderService, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    return CancelOrderService(repo), repo


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING]
)
def test_cancels_order_before_dispatch(status: OrderStatus):
    order = _order(status=status)
    service, repo = _service(order)

    result = service.cancel(CancelOrderCommand(user_id=USER, order_id=order.id))

    assert result.status is OrderStatus.CANCELLED
    # Persisted through the repository, not merely mutated on a transient aggregate.
    assert repo.get(order.id, user_id=USER).status is OrderStatus.CANCELLED


def test_cancel_records_history_entry():
    order = _order(status=OrderStatus.CONFIRMED)
    service, _ = _service(order)

    result = service.cancel(CancelOrderCommand(user_id=USER, order_id=order.id))

    assert len(result.status_history) == 1
    change = result.status_history[-1]
    assert change.from_status is OrderStatus.CONFIRMED
    assert change.to_status is OrderStatus.CANCELLED


def test_unknown_id_raises_not_found():
    service, _ = _service(_order())

    with pytest.raises(OrderNotFoundError):
        service.cancel(CancelOrderCommand(user_id=USER, order_id=uuid.uuid4()))


def test_other_users_order_raises_not_found_and_is_untouched():
    other = uuid.uuid4()
    theirs = _order(user_id=other, status=OrderStatus.PENDING)
    service, repo = _service(theirs)

    # The order exists, but not for this caller: indistinguishable from unknown (no enumeration).
    with pytest.raises(OrderNotFoundError):
        service.cancel(CancelOrderCommand(user_id=USER, order_id=theirs.id))

    # And it must be completely untouched for its real owner.
    assert repo.get(theirs.id, user_id=other).status is OrderStatus.PENDING


@pytest.mark.parametrize(
    "status", [OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED, OrderStatus.CANCELLED]
)
def test_cancel_after_dispatch_raises_illegal(status: OrderStatus):
    order = _order(status=status)
    service, repo = _service(order)

    with pytest.raises(IllegalOrderTransitionError):
        service.cancel(CancelOrderCommand(user_id=USER, order_id=order.id))

    # The state machine leaves the aggregate untouched on an illegal move.
    assert repo.get(order.id, user_id=USER).status is status


def test_not_found_error_carries_the_requested_id():
    service, _ = _service()
    missing = uuid.uuid4()

    with pytest.raises(OrderNotFoundError) as exc_info:
        service.cancel(CancelOrderCommand(user_id=USER, order_id=missing))

    assert exc_info.value.order_id == missing
