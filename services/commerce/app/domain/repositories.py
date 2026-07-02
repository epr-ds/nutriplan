"""Ports for the Commerce domain — persistence abstractions the application depends on."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol

from app.domain.enums import OrderStatus
from app.domain.order import Order


class OrderRepository(Protocol):
    """Persistence port for the :class:`~app.domain.order.Order` aggregate."""

    def add(self, order: Order) -> Order:
        """Persist a new order (with its items) and return it."""
        ...

    def get(self, order_id: uuid.UUID, *, user_id: uuid.UUID) -> Order | None:
        """Load an order owned by ``user_id``, or ``None`` if absent/not theirs."""
        ...

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        from_date: date | None = None,
    ) -> list[Order]:
        """List the user's orders, newest first, optionally filtered by status/date."""
        ...
