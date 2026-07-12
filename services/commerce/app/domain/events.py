"""Commerce domain events.

The ``Order`` aggregate *records* events as its state changes (COM-106); the actual publishing to
a message bus is wired later (COM-109). Keeping the event a plain, immutable value object lets the
aggregate stay free of any transport/broker concern — a consumer drains them via
:meth:`~app.domain.order.Order.pull_events`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import OrderStatus


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
