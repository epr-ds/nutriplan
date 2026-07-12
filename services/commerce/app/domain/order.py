"""The ``Order`` aggregate root and its ``OrderItem`` entities.

An order groups the caller's chosen fulfilment, delivery address, and priced line items. It maps
onto the OpenAPI ``OrderResponse`` (see :mod:`app.api.schemas`).

The aggregate also owns the order **lifecycle state machine** (COM-106): only the transitions in
:data:`_ALLOWED_TRANSITIONS` are permitted, every move is timestamped into ``status_history``, and
an :class:`~app.domain.events.OrderStatusChanged` event is recorded for a downstream bus to drain
(COM-109). An illegal move raises :class:`~app.domain.errors.IllegalOrderTransitionError`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import IllegalOrderTransitionError
from app.domain.events import OrderStatusChanged
from app.domain.money import Money

# The order lifecycle as a directed graph. An order progresses forward through fulfilment and may be
# cancelled at any point *before* it is dispatched; once in transit it can only be delivered, and
# ``delivered``/``cancelled`` are terminal. Enumerating it here (rather than scattering ``if``
# checks) keeps the policy in one auditable place and makes both legal and illegal moves testable.
_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.PREPARING, OrderStatus.CANCELLED}),
    OrderStatus.PREPARING: frozenset({OrderStatus.IN_TRANSIT, OrderStatus.CANCELLED}),
    OrderStatus.IN_TRANSIT: frozenset({OrderStatus.DELIVERED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class OrderStatusChange:
    """A single, immutable entry in an order's transition history (COM-106).

    ``from_status`` is always populated — history records *transitions*, so a freshly created order
    has an empty history until its first move.
    """

    from_status: OrderStatus
    to_status: OrderStatus
    occurred_at: datetime


@dataclass
class OrderItem:
    name: str
    quantity: Decimal
    unit: str
    unit_price: Money
    line_total: Money
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Order:
    user_id: uuid.UUID
    fulfillment_type: FulfillmentType
    delivery_address: Address
    delivery_date: date
    delivery_time_slot: str
    status: OrderStatus = OrderStatus.PENDING
    provider_id: str | None = None
    notes: str | None = None
    subtotal: Money = field(default_factory=Money.zero)
    delivery_fee: Money = field(default_factory=Money.zero)
    total: Money = field(default_factory=Money.zero)
    estimated_delivery: datetime | None = None
    tracking_url: str | None = None
    items: list[OrderItem] = field(default_factory=list)
    status_history: list[OrderStatusChange] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    # Recorded on each transition, drained by pull_events(); excluded from equality/repr so it never
    # perturbs value comparisons or leaks into logs.
    _events: list[OrderStatusChanged] = field(
        default_factory=list, init=False, compare=False, repr=False
    )

    def add_item(self, item: OrderItem) -> None:
        """Append a line item to the order."""
        self.items.append(item)

    @property
    def is_terminal(self) -> bool:
        """True when the order can no longer transition (``delivered`` or ``cancelled``)."""
        return not _ALLOWED_TRANSITIONS[self.status]

    def can_transition_to(self, target: OrderStatus) -> bool:
        """Whether moving to ``target`` is permitted from the current status."""
        return target in _ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, target: OrderStatus, *, occurred_at: datetime | None = None) -> None:
        """Move the order to ``target``, enforcing the lifecycle graph.

        On success the move is appended to ``status_history`` with its timestamp, an
        :class:`OrderStatusChanged` event is recorded, and ``updated_at`` is bumped. An illegal move
        raises :class:`IllegalOrderTransitionError` and leaves the aggregate untouched.
        """
        if not self.can_transition_to(target):
            raise IllegalOrderTransitionError(self.status, target)
        when = occurred_at or _utcnow()
        previous = self.status
        self.status_history.append(OrderStatusChange(previous, target, when))
        self._events.append(
            OrderStatusChanged(
                order_id=self.id,
                user_id=self.user_id,
                from_status=previous,
                to_status=target,
                occurred_at=when,
            )
        )
        self.status = target
        self.updated_at = when

    def confirm(self, *, occurred_at: datetime | None = None) -> None:
        """Transition ``pending → confirmed``."""
        self.transition_to(OrderStatus.CONFIRMED, occurred_at=occurred_at)

    def start_preparing(self, *, occurred_at: datetime | None = None) -> None:
        """Transition ``confirmed → preparing``."""
        self.transition_to(OrderStatus.PREPARING, occurred_at=occurred_at)

    def mark_in_transit(self, *, occurred_at: datetime | None = None) -> None:
        """Transition ``preparing → in_transit`` (dispatch)."""
        self.transition_to(OrderStatus.IN_TRANSIT, occurred_at=occurred_at)

    def mark_delivered(self, *, occurred_at: datetime | None = None) -> None:
        """Transition ``in_transit → delivered``."""
        self.transition_to(OrderStatus.DELIVERED, occurred_at=occurred_at)

    def cancel(self, *, occurred_at: datetime | None = None) -> None:
        """Cancel the order (allowed only before it is dispatched)."""
        self.transition_to(OrderStatus.CANCELLED, occurred_at=occurred_at)

    def pull_events(self) -> list[OrderStatusChanged]:
        """Return and clear the events recorded since the last drain."""
        events = list(self._events)
        self._events.clear()
        return events
