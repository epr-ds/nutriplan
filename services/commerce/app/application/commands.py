"""Application commands — the transport-agnostic inputs to the use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from app.domain.address import Address
from app.domain.enums import FulfillmentType, PaymentMethodType


@dataclass(frozen=True)
class CreateOrderCommand:
    """Everything needed to turn a meal plan into an order, with auth already resolved.

    ``user_id`` is the authenticated caller; ``meal_plan_id`` is validated for ownership by the
    Dietary service when the plan is fetched (the caller's token is forwarded out-of-band). When a
    card ``payment_method_type`` and ``payment_token`` are supplied the order is charged inline at
    creation (COM-202); other methods (or none) leave the order ``pending`` to settle later.
    """

    user_id: uuid.UUID
    meal_plan_id: str
    fulfillment_type: FulfillmentType
    delivery_address: Address
    delivery_date: date
    delivery_time_slot: str
    provider_id: str | None = None
    notes: str | None = None
    payment_method_type: PaymentMethodType | None = None
    payment_token: str | None = None


@dataclass(frozen=True)
class CancelOrderCommand:
    """A caller-scoped request to cancel a single order (COM-107).

    ``user_id`` is the authenticated caller; the order is only cancellable when it belongs to them,
    so an unknown id and another user's order are indistinguishable (no enumeration). Whether the
    order may actually be cancelled from its current state is decided by the domain state machine.
    """

    user_id: uuid.UUID
    order_id: uuid.UUID
