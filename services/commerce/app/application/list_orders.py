"""COM-104 use case: list the caller's orders with filters and pagination.

A thin read-side application service over the :class:`~app.domain.repositories.OrderRepository`
port. It keeps the router free of persistence concerns and translates the query's 1-based ``page``
into the repository's row ``offset``. Ownership scoping, newest-first ordering, and the status/date
filters are enforced by the repository.
"""

from __future__ import annotations

from app.application.queries import ListOrdersQuery
from app.domain.order import Order
from app.domain.repositories import OrderRepository


class ListOrdersService:
    """Lists a user's orders (COM-104)."""

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def list(self, query: ListOrdersQuery) -> list[Order]:
        return self._orders.list_for_user(
            query.user_id,
            status=query.status,
            from_date=query.from_date,
            limit=query.limit,
            offset=query.offset,
        )
