"""The ``Order`` aggregate root and its ``OrderItem`` entities.

An order groups the caller's chosen fulfilment, delivery address, and priced line items. It maps
onto the OpenAPI ``OrderResponse`` (see :mod:`app.api.schemas`). Pricing (COM-103) and status
transitions (COM-106) arrive in later stories; here the aggregate is the persistence-backed model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def add_item(self, item: OrderItem) -> None:
        """Append a line item to the order."""
        self.items.append(item)
