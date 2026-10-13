"""Ports for the Commerce domain — persistence abstractions the application depends on."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol

from app.domain.enums import OrderStatus
from app.domain.order import Order
from app.domain.payment_method import SavedPaymentMethod


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


class PaymentMethodRepository(Protocol):
    """Persistence port for the caller's saved payment methods (COM-207).

    Every operation is owner-scoped by ``user_id`` so one user can neither list, read nor delete
    another's stored instrument; an unknown id and a not-owned id are therefore indistinguishable.
    """

    def add(self, method: SavedPaymentMethod) -> SavedPaymentMethod:
        """Persist a newly tokenized payment method and return it."""
        ...

    def list_for_user(self, user_id: uuid.UUID) -> list[SavedPaymentMethod]:
        """List the user's saved payment methods, newest first."""
        ...

    def get(self, method_id: uuid.UUID, *, user_id: uuid.UUID) -> SavedPaymentMethod | None:
        """Load one of the user's saved methods, or ``None`` if absent/not theirs."""
        ...

    def delete(self, method_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        """Delete one of the user's saved methods; return ``True`` iff a row was removed."""
        ...
