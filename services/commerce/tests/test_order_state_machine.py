"""COM-106: order lifecycle state machine — enforced transitions, history, and events."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import IllegalOrderTransitionError
from app.domain.events import OrderStatusChanged
from app.domain.order import Order

_LEGAL = [
    (OrderStatus.PENDING, OrderStatus.CONFIRMED),
    (OrderStatus.PENDING, OrderStatus.CANCELLED),
    (OrderStatus.CONFIRMED, OrderStatus.PREPARING),
    (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    (OrderStatus.PREPARING, OrderStatus.IN_TRANSIT),
    (OrderStatus.PREPARING, OrderStatus.CANCELLED),
    (OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED),
]

# Every (from, to) pair that is NOT in the legal set and is not a no-op self-loop.
_ILLEGAL = [
    (current, target)
    for current in OrderStatus
    for target in OrderStatus
    if current != target and (current, target) not in _LEGAL
]

_TERMINAL = [OrderStatus.DELIVERED, OrderStatus.CANCELLED]


def _make_order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    return Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(
            street="Av. Reforma 100",
            city="Ciudad de Mexico",
            state="CDMX",
            zip_code="06600",
            country="MX",
        ),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
    )


@pytest.mark.parametrize(("current", "target"), _LEGAL)
def test_legal_transition_updates_status(current: OrderStatus, target: OrderStatus) -> None:
    order = _make_order(current)

    order.transition_to(target)

    assert order.status is target


@pytest.mark.parametrize(("current", "target"), _ILLEGAL)
def test_illegal_transition_is_rejected(current: OrderStatus, target: OrderStatus) -> None:
    order = _make_order(current)

    with pytest.raises(IllegalOrderTransitionError):
        order.transition_to(target)

    # The aggregate is untouched on rejection: no status change, no history, no event.
    assert order.status is current
    assert order.status_history == []
    assert order.pull_events() == []


@pytest.mark.parametrize("status", _TERMINAL)
def test_terminal_states_allow_no_transition(status: OrderStatus) -> None:
    order = _make_order(status)

    assert order.is_terminal is True
    for target in OrderStatus:
        if target is status:
            continue
        with pytest.raises(IllegalOrderTransitionError):
            order.transition_to(target)


@pytest.mark.parametrize("status", [s for s in OrderStatus if s not in _TERMINAL])
def test_non_terminal_states_are_not_terminal(status: OrderStatus) -> None:
    assert _make_order(status).is_terminal is False


def test_self_transition_is_rejected() -> None:
    order = _make_order(OrderStatus.PENDING)

    with pytest.raises(IllegalOrderTransitionError):
        order.transition_to(OrderStatus.PENDING)


def test_transition_records_history_with_timestamp() -> None:
    order = _make_order(OrderStatus.PENDING)
    when = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)

    order.transition_to(OrderStatus.CONFIRMED, occurred_at=when)

    assert len(order.status_history) == 1
    change = order.status_history[0]
    assert change.from_status is OrderStatus.PENDING
    assert change.to_status is OrderStatus.CONFIRMED
    assert change.occurred_at == when
    assert order.updated_at == when


def test_history_accumulates_in_order() -> None:
    order = _make_order(OrderStatus.PENDING)

    order.confirm()
    order.start_preparing()
    order.mark_in_transit()
    order.mark_delivered()

    assert [(c.from_status, c.to_status) for c in order.status_history] == [
        (OrderStatus.PENDING, OrderStatus.CONFIRMED),
        (OrderStatus.CONFIRMED, OrderStatus.PREPARING),
        (OrderStatus.PREPARING, OrderStatus.IN_TRANSIT),
        (OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED),
    ]
    assert order.status is OrderStatus.DELIVERED


def test_default_timestamp_is_populated() -> None:
    order = _make_order(OrderStatus.PENDING)

    order.confirm()

    assert order.status_history[0].occurred_at is not None
    assert order.updated_at == order.status_history[0].occurred_at


def test_transition_records_event() -> None:
    order = _make_order(OrderStatus.PENDING)
    when = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)

    order.transition_to(OrderStatus.CONFIRMED, occurred_at=when)
    events = order.pull_events()

    assert events == [
        OrderStatusChanged(
            order_id=order.id,
            user_id=order.user_id,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.CONFIRMED,
            occurred_at=when,
        )
    ]


def test_pull_events_drains() -> None:
    order = _make_order(OrderStatus.PENDING)
    order.confirm()
    order.start_preparing()

    first = order.pull_events()
    assert len(first) == 2
    # A second drain is empty — events are consumed once.
    assert order.pull_events() == []


def test_convenience_methods_map_to_expected_targets() -> None:
    order = _make_order(OrderStatus.PENDING)
    order.confirm()
    assert order.status is OrderStatus.CONFIRMED
    order.start_preparing()
    assert order.status is OrderStatus.PREPARING
    order.mark_in_transit()
    assert order.status is OrderStatus.IN_TRANSIT
    order.mark_delivered()
    assert order.status is OrderStatus.DELIVERED


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING]
)
def test_cancel_allowed_before_dispatch(status: OrderStatus) -> None:
    order = _make_order(status)

    order.cancel()

    assert order.status is OrderStatus.CANCELLED


@pytest.mark.parametrize(
    "status", [OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED, OrderStatus.CANCELLED]
)
def test_cancel_rejected_from_dispatch_onward(status: OrderStatus) -> None:
    order = _make_order(status)

    with pytest.raises(IllegalOrderTransitionError):
        order.cancel()


def test_illegal_convenience_method_raises() -> None:
    order = _make_order(OrderStatus.PENDING)

    # Cannot mark a pending order delivered — only in_transit → delivered is legal.
    with pytest.raises(IllegalOrderTransitionError):
        order.mark_delivered()


def test_can_transition_to_reflects_graph() -> None:
    order = _make_order(OrderStatus.PENDING)

    assert order.can_transition_to(OrderStatus.CONFIRMED) is True
    assert order.can_transition_to(OrderStatus.CANCELLED) is True
    assert order.can_transition_to(OrderStatus.DELIVERED) is False
