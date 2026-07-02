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
