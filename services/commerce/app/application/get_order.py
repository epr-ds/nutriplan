"""COM-105 use case: fetch one of the caller's orders by id.

A thin read-side application service over the :class:`~app.domain.repositories.OrderRepository`
port. The repository read is owner-scoped, so an order that does not exist and one that belongs to
another user both come back as ``None``; either way this raises :class:`OrderNotFoundError`, which
the API layer renders as ``404`` — a caller can never tell the two apart (no enumeration).
"""

from __future__ import annotations

from app.application.queries import GetOrderQuery
from app.domain.errors import OrderNotFoundError
from app.domain.order import Order
from app.domain.repositories import OrderRepository


class GetOrderService:
    """Fetches a single order owned by the caller (COM-105)."""

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def get(self, query: GetOrderQuery) -> Order:
        order = self._orders.get(query.order_id, user_id=query.user_id)
        if order is None:
            raise OrderNotFoundError(query.order_id)
        return order
