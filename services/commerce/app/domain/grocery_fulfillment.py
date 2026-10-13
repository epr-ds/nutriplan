"""COM-408: how a grocery provider's fulfilment progress maps onto our own order lifecycle.

The ACL (COM-402) already normalises every provider's own status vocabulary onto the canonical
:class:`~app.domain.grocery_catalog.GroceryOrderStatus`. This module is the second half of that
translation: it maps that canonical grocery status onto the
:class:`~app.domain.enums.OrderStatus` of the COM-106 state machine, which is what the rest of the
platform (and the client) actually reasons about.

The two vocabularies are deliberately *not* the same shape, so the table below is the single place
the difference is decided:

* ``pending`` means "the provider has not accepted the order yet" -- our order is already at least
  ``confirmed`` by the time it is placed, so it maps to *no move at all*;
* ``out_for_delivery`` is the provider's word for our ``in_transit``;
* ``failed`` is not a lifecycle state of ours -- a provider that cannot fulfil the order leaves it
  ``cancelled``, same as an explicit provider cancellation;
* ``unknown`` (an unrecognised provider string that the ACL refused to leak) maps to no move, so an
  unreadable poll never drags an order backwards or sideways.
"""

from __future__ import annotations

from app.domain.enums import OrderStatus
from app.domain.grocery_catalog import GroceryOrderStatus

# The provider's canonical status -> the order state it implies. ``None`` means "this tells us
# nothing new about our lifecycle", which the settler treats as a no-op rather than an error.
_ORDER_STATUS_FOR: dict[GroceryOrderStatus, OrderStatus | None] = {
    GroceryOrderStatus.PENDING: None,
    GroceryOrderStatus.CONFIRMED: OrderStatus.CONFIRMED,
    GroceryOrderStatus.PREPARING: OrderStatus.PREPARING,
    GroceryOrderStatus.OUT_FOR_DELIVERY: OrderStatus.IN_TRANSIT,
    GroceryOrderStatus.DELIVERED: OrderStatus.DELIVERED,
    GroceryOrderStatus.CANCELLED: OrderStatus.CANCELLED,
    GroceryOrderStatus.FAILED: OrderStatus.CANCELLED,
    GroceryOrderStatus.UNKNOWN: None,
}

# The forward lifecycle as an ordered path. Status sync is a *poll*, so a provider can easily report
# a state two or three steps ahead of what we last saw (we simply were not looking while it moved).
# Ordering the path lets the settler walk the intervening transitions rather than either refusing
# the report or jumping the state machine -- every step is still recorded and timestamped.
FORWARD_PATH: tuple[OrderStatus, ...] = (
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.IN_TRANSIT,
    OrderStatus.DELIVERED,
)


def order_status_for(status: GroceryOrderStatus) -> OrderStatus | None:
    """Return the order state a provider's grocery status implies, or ``None`` for "no move"."""
    return _ORDER_STATUS_FOR.get(status)


def steps_between(current: OrderStatus, target: OrderStatus) -> tuple[OrderStatus, ...]:
    """Return the forward transitions taking ``current`` to ``target`` (empty when not forward).

    Both states must lie on :data:`FORWARD_PATH`; a target at or behind the current state yields no
    steps, which is how an out-of-date (or redelivered) provider report becomes an idempotent no-op.
    """
    if current not in FORWARD_PATH or target not in FORWARD_PATH:
        return ()
    start = FORWARD_PATH.index(current)
    end = FORWARD_PATH.index(target)
    if end <= start:
        return ()
    return FORWARD_PATH[start + 1 : end + 1]
