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


@dataclass(frozen=True)
class AddPaymentMethodCommand:
    """Everything needed to store a tokenized payment method for the caller (COM-207).

    ``user_id`` is the authenticated caller. ``token`` is the durable provider handle produced by
    on-device tokenization — **never** a PAN. The display metadata (``brand``/``last4``/expiry) is
    optional: cards carry it, wallets such as PayPal do not.
    """

    user_id: uuid.UUID
    type: PaymentMethodType
    token: str
    brand: str | None = None
    last4: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None


@dataclass(frozen=True)
class DeletePaymentMethodCommand:
    """A caller-scoped request to delete one saved payment method (COM-207).

    ``user_id`` is the authenticated caller; the method is only deletable when it belongs to them,
    so an unknown id and another user's method are indistinguishable (no enumeration).
    """

    user_id: uuid.UUID
    payment_method_id: uuid.UUID
