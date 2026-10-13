"""Commerce domain events.

The ``Order`` aggregate *records* events as it is placed and as its state changes (COM-106); the
actual publishing to a message bus is wired in COM-109. Keeping each event a plain, immutable value
object lets the aggregate stay free of any transport/broker concern -- a consumer drains them via
:meth:`~app.domain.order.Order.pull_events` and hands them to an
:class:`~app.events.publisher.EventPublisher`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import OrderStatus


@dataclass(frozen=True)
class OrderCreated:
    """Emitted once when an order is first placed (COM-109).

    Carries just the identity of the new order and its owner -- enough for a downstream handler
    (notifications, analytics) to react to "an order was placed" and, if it needs more, look the
    order up. It is recorded by :meth:`~app.domain.order.Order.record_created` (never in the
    constructor, so rehydrating a stored order from the database emits nothing).
    """

    order_id: uuid.UUID
    user_id: uuid.UUID
    occurred_at: datetime


@dataclass(frozen=True)
class OrderStatusChanged:
    """Emitted whenever an order moves between lifecycle states (COM-106).

    Carries enough context for a downstream handler (notifications, analytics, COM-109's bus) to act
    without loading the aggregate: which order, whose, and the exact transition with its timestamp.
    """

    order_id: uuid.UUID
    user_id: uuid.UUID
    from_status: OrderStatus
    to_status: OrderStatus
    occurred_at: datetime


# The closed set of events the order aggregate can record and a consumer can drain. Kept as a union
# (rather than a base class) so each event stays a flat, frozen value object and exhaustive handling
# is checkable.
DomainEvent = OrderCreated | OrderStatusChanged
