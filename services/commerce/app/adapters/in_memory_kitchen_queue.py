"""An in-process kitchen queue for dev, CI, and tests (COM-303).

There is no real kitchen system to integrate with yet, so this adapter is the honest default (like
:class:`~app.application.ports.EmptySlotInventory` for slot inventory): it records each routed
:class:`~app.domain.kitchen.KitchenTicket` -- so a test can assert exactly what was handed off --
and logs the routing so it is observable in a running service. A durable adapter (an HTTP call to a
kitchen, or a stream a kitchen consumes) can replace it behind the ``KitchenQueue`` port without
touching the routing use case. The order's ``order.confirmed`` domain event is already published to
the bus (COM-109), so a future kitchen consumer has a durable signal regardless.
"""

from __future__ import annotations

import logging

from app.domain.kitchen import KitchenTicket

logger = logging.getLogger(__name__)


class InMemoryKitchenQueue:
    """Satisfies the ``KitchenQueue`` port by recording (and logging) routed tickets."""

    def __init__(self) -> None:
        self.tickets: list[KitchenTicket] = []

    def route(self, ticket: KitchenTicket) -> None:
        self.tickets.append(ticket)
        logger.info(
            "Routed order %s to the kitchen queue (%d item(s), slot %s)",
            ticket.order_id,
            len(ticket.items),
            ticket.delivery_time_slot,
        )
