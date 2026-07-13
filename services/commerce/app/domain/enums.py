"""Commerce domain enumerations mirroring the ``contracts/commerce.openapi.yaml`` enums."""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    """Lifecycle states of an order (state transitions are enforced in COM-106)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class FulfillmentType(StrEnum):
    DARK_KITCHEN = "dark_kitchen"
    GROCERY_DELIVERY = "grocery_delivery"
    PICKUP = "pickup"


class ProviderType(StrEnum):
    DARK_KITCHEN = "dark_kitchen"
    GROCERY = "grocery"


class PaymentMethodType(StrEnum):
    """How the caller chose to pay, mirroring the ``PaymentMethodRequest.type`` contract enum.

    Cards (``credit_card``/``debit_card``) are charged synchronously at order creation (COM-202);
    the remaining methods settle asynchronously via a later provider webhook (OXXO/SPEI in
    COM-203/204, PayPal in COM-205) and leave the order ``pending`` until then.
    """

    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    OXXO = "oxxo"
    SPEI = "spei"

    @property
    def is_card(self) -> bool:
        """True for the card methods charged inline at checkout (COM-202)."""
        return self in {PaymentMethodType.CREDIT_CARD, PaymentMethodType.DEBIT_CARD}
