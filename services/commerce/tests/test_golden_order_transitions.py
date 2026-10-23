"""COM-806: the order lifecycle against a golden transition table.

``tests/golden/order_transitions.json`` holds the lifecycle graph and the outcome of every order
command from every status: the new status, an idempotent no-op, or a rejection. Every illegal move
must raise :class:`IllegalOrderTransitionError` and leave the order exactly as it was -- status,
history, payment fields and events -- so a change to the lifecycle has to change the golden file
on purpose.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import IllegalOrderTransitionError
from app.domain.events import OrderStatusChanged
from app.domain.order import Order

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "order_transitions.json").read_text("utf-8")
)
_GRAPH: dict[str, list[str]] = _GOLDEN["graph"]
_COMMANDS: dict[str, dict[str, str]] = _GOLDEN["commands"]

_AT = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)
_ADDRESS = Address(street="Reforma 222", city="CDMX", state="CDMX", zip_code="06600", country="MX")

# How each golden command is applied to an order.
_APPLY: dict[str, Callable[[Order], None]] = {
    "cancel": lambda order: order.cancel(occurred_at=_AT),
    "mark_paid": lambda order: order.mark_paid(provider="fake", charge_id="ch_1", occurred_at=_AT),
    "confirm_payment": lambda order: order.confirm_payment(charge_id="ch_1", occurred_at=_AT),
    "fail_payment": lambda order: order.fail_payment(occurred_at=_AT),
    "report_preparing": lambda order: order.report_preparing(occurred_at=_AT),
    "report_dispatched": lambda order: order.report_dispatched(occurred_at=_AT),
    "mark_delivered": lambda order: order.mark_delivered(occurred_at=_AT),
}

_CASES = [
    (command, status, outcome)
    for command, outcomes in _COMMANDS.items()
    for status, outcome in outcomes.items()
]
_CASE_IDS = [f"{command}-from-{status}" for command, status, _ in _CASES]


def _order(status: OrderStatus) -> Order:
    return Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_ADDRESS,
        delivery_date=date(2026, 11, 2),
        delivery_time_slot="13:00-15:00",
        status=status,
    )


def _snapshot(order: Order) -> dict[str, Any]:
    """Everything a rejected or idempotent command must leave as it was."""
    return {
        "status": order.status,
        "history": list(order.status_history),
        "updated_at": order.updated_at,
        "payment_status": order.payment_status,
        "payment_provider": order.payment_provider,
        "payment_charge_id": order.payment_charge_id,
    }


# --- the golden table itself ----------------------------------------------------------------------


def test_the_golden_covers_every_status():
    statuses = {status.value for status in OrderStatus}

    assert set(_GRAPH) == statuses
    for command, outcomes in _COMMANDS.items():
        assert set(outcomes) == statuses, command


def test_every_golden_command_is_applied():
    assert set(_COMMANDS) == set(_APPLY)


def test_the_golden_outcomes_follow_the_graph():
    """A command only ever moves an order along an edge of the graph."""
    for command, outcomes in _COMMANDS.items():
        for status, outcome in outcomes.items():
            if outcome not in ("rejected", "unchanged"):
                assert outcome in _GRAPH[status], f"{command} from {status}"


# --- the domain graph -----------------------------------------------------------------------------


@pytest.mark.parametrize("current", list(OrderStatus), ids=lambda status: status.value)
def test_the_domain_graph_is_the_golden_one(current: OrderStatus):
    order = _order(current)
    allowed = {target.value for target in OrderStatus if order.can_transition_to(target)}

    assert allowed == set(_GRAPH[current.value])
    terminal = not _GRAPH[current.value]
    assert order.is_terminal is terminal


@pytest.mark.parametrize("current", list(OrderStatus), ids=lambda status: status.value)
def test_every_move_off_the_graph_is_rejected_and_changes_nothing(current: OrderStatus):
    for target in OrderStatus:
        if target.value in _GRAPH[current.value]:
            continue
        order = _order(current)
        before = _snapshot(order)

        with pytest.raises(IllegalOrderTransitionError):
            order.transition_to(target, occurred_at=_AT)

        assert _snapshot(order) == before, target
        assert order.pull_events() == [], target


# --- the commands ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("command", "status", "outcome"), _CASES, ids=_CASE_IDS)
def test_each_command_from_each_status_matches_the_golden(command: str, status: str, outcome: str):
    order = _order(OrderStatus(status))
    before = _snapshot(order)

    if outcome == "rejected":
        with pytest.raises(IllegalOrderTransitionError):
            _APPLY[command](order)
        assert _snapshot(order) == before
        assert order.pull_events() == []
        return

    _APPLY[command](order)

    if outcome == "unchanged":
        assert _snapshot(order) == before
        assert order.pull_events() == []
        return
    target = OrderStatus(outcome)
    assert order.status is target
    history = [(change.from_status, change.to_status) for change in order.status_history]
    assert history == [(OrderStatus(status), target)]
    assert order.updated_at == _AT
    events = order.pull_events()
    assert events == [
        OrderStatusChanged(
            order_id=order.id,
            user_id=order.user_id,
            from_status=OrderStatus(status),
            to_status=target,
            occurred_at=_AT,
        )
    ]
