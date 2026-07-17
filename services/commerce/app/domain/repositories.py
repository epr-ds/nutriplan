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

    def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        """Load an order by id alone, or ``None`` if absent.

        Unlike :meth:`get` this is **not** owner-scoped: it exists for the payment-webhook handler
        (COM-206), which is authenticated by the provider's signature rather than a user token and
        so has no ``user_id`` to scope by. It must never back a user-facing read path.
        """
        ...

    def update(self, order: Order) -> Order:
        """Persist mutations to an existing order (status + appended history) and return it."""
        ...

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        from_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Order]:
        """List the user's orders, newest first, with optional filters and pagination."""
        ...
