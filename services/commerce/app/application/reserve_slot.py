"""COM-304 use case: reserve (and release) a dark-kitchen delivery slot for an order.

Dark-kitchen fulfilment offers each delivery window a limited daily capacity (COM-302). This thin
application service turns that read-only availability into a **write**: when an order is placed it
books one unit of the chosen window's capacity, and when the order is cancelled it hands the unit
back. It is deliberately gated to :attr:`~app.domain.enums.FulfillmentType.DARK_KITCHEN` orders --
pickup and grocery orders do not consume kitchen slots -- so wiring it into the shared create/cancel
flows is a no-op for every other fulfilment type.

Capacity itself lives in the :class:`~app.application.ports.SlotReservationStore` (the count-guarded
insert that raises :class:`~app.domain.errors.SlotUnavailableError` on a full window); this service
only supplies the policy inputs -- the window key is the order's delivery postcode, and the ceiling
is the service area's configured ``slot_capacity``.
"""

from __future__ import annotations

import uuid

from app.application.ports import SlotReservationStore
from app.domain.enums import FulfillmentType
from app.domain.fulfillment import DarkKitchenServiceArea
from app.domain.order import Order


class ReserveDeliverySlotService:
    """Books/frees a dark-kitchen delivery slot as orders are created and cancelled (COM-304)."""

    def __init__(self, service_area: DarkKitchenServiceArea, store: SlotReservationStore) -> None:
        self._service_area = service_area
        self._store = store

    def reserve_for(self, order: Order) -> None:
        """Book one unit of the order's delivery-window capacity, if it is a dark-kitchen order.

        A non-dark-kitchen order consumes no kitchen slot, so this is a no-op for it. For a
        dark-kitchen order a full window raises
        :class:`~app.domain.errors.SlotUnavailableError` (mapped to ``409``); because reserving
        runs before the order is persisted, a full slot places no order at all.
        """
        if order.fulfillment_type is not FulfillmentType.DARK_KITCHEN:
            return
        self._store.reserve(
            zip_code=order.delivery_address.zip_code,
            delivery_date=order.delivery_date,
            slot=order.delivery_time_slot,
            order_id=order.id,
            capacity=self._service_area.slot_capacity,
        )

    def release_for(self, order_id: uuid.UUID) -> None:
        """Release any slot held for ``order_id`` (idempotent; safe for any order).

        Deleting a non-existent reservation is a no-op, so this is safe to call for a cancelled
        order regardless of its fulfilment type or whether it ever held a slot.
        """
        self._store.release(order_id=order_id)
