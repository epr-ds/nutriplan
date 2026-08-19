"""Dark-kitchen routing + status-sync value objects (COM-303).

A confirmed dark-kitchen order is handed to a kitchen as an immutable :class:`KitchenTicket` -- the
minimum a kitchen needs to cook and dispatch it (what, when, where-slot), carrying the order id so
the kitchen can later report progress back. Those reports arrive as a signed
:class:`KitchenWebhookEvent`: a :attr:`KitchenEventType.PREPARING` signal advances the order to
``preparing`` and a :attr:`KitchenEventType.DISPATCHED` signal advances it to ``in_transit`` (the
mapping is applied by the idempotent ``Order.report_*`` methods). All three are flat, frozen value
objects so the domain stays free of any queue/transport concern.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.order import Order


class KitchenEventType(StrEnum):
    """What a kitchen reports back about an order it is fulfilling (COM-303).

    Deliberately just the two signals that move the order forward: ``kitchen.preparing`` (the
    kitchen has started cooking -> ``preparing``) and ``kitchen.dispatched`` (the order has left
    the kitchen -> ``in_transit``). The ``kitchen.`` prefix keeps them distinct from the payment
    webhook's ``payment.*`` events on the shared webhook surface.
    """

    PREPARING = "kitchen.preparing"
    DISPATCHED = "kitchen.dispatched"


@dataclass(frozen=True)
class KitchenWebhookEvent:
    """A kitchen's signed status callback (COM-303).

    ``reference`` is the order id the kitchen was handed on the routing ticket, so the handler can
    find the order and apply the :class:`KitchenEventType` mapping to its lifecycle state.
    """

    type: KitchenEventType
    reference: str


@dataclass(frozen=True)
class KitchenTicketItem:
    """A single line a kitchen must prepare: what, and how much."""

    name: str
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class KitchenTicket:
    """The routing payload handed to a kitchen for a confirmed dark-kitchen order (COM-303).

    Carries only what a kitchen needs -- the order id (so it can report progress back), whose order
    it is, the delivery date and time window, an optional provider hint, the line items to cook, and
    any delivery notes. It is built from a confirmed :class:`~app.domain.order.Order` by
    :meth:`for_order` and never mutated.
    """

    order_id: uuid.UUID
    user_id: uuid.UUID
    delivery_date: date
    delivery_time_slot: str
    provider_id: str | None
    notes: str | None
    items: tuple[KitchenTicketItem, ...]

    @classmethod
    def for_order(cls, order: Order) -> KitchenTicket:
        """Build a ticket from a confirmed dark-kitchen order."""
        return cls(
            order_id=order.id,
            user_id=order.user_id,
            delivery_date=order.delivery_date,
            delivery_time_slot=order.delivery_time_slot,
            provider_id=order.provider_id,
            notes=order.notes,
            items=tuple(
                KitchenTicketItem(name=item.name, quantity=item.quantity, unit=item.unit)
                for item in order.items
            ),
        )
