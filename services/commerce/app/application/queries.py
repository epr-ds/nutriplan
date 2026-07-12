"""Application queries — the transport-agnostic inputs to the read use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from app.domain.enums import OrderStatus


@dataclass(frozen=True)
class GetOrderQuery:
    """A caller-scoped request for a single order by id (COM-105).

    ``user_id`` is the authenticated caller; the order is only returned when it belongs to them, so
    an unknown id and another user's id are indistinguishable (no enumeration).
    """

    user_id: uuid.UUID
    order_id: uuid.UUID


@dataclass(frozen=True)
class ListOrdersQuery:
    """A caller-scoped, filtered, paginated request for a user's orders (COM-104).

    ``user_id`` is the authenticated caller (results are always scoped to them). ``page`` is
    1-based and ``limit`` is the page size; both are validated at the HTTP edge to match the
    contract (page >= 1, 1 <= limit <= 100).
    """

    user_id: uuid.UUID
    status: OrderStatus | None = None
    from_date: date | None = None
    page: int = 1
    limit: int = 20

    @property
    def offset(self) -> int:
        """Zero-based row offset for the requested page."""
        return (self.page - 1) * self.limit
