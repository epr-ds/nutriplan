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


@dataclass(frozen=True)
class ListPaymentMethodsQuery:
    """A caller-scoped request for the user's saved payment methods (COM-207).

    ``user_id`` is the authenticated caller; results are always scoped to them.
    """

    user_id: uuid.UUID


@dataclass(frozen=True)
class SyncGroceryOrderQuery:
    """A caller-scoped request to refresh an order's status from its grocery provider (COM-408).

    ``user_id`` is the authenticated caller; the order is only synced when it belongs to them, so
    an unknown id and another user's id are indistinguishable (no enumeration).
    """

    user_id: uuid.UUID
    order_id: uuid.UUID


@dataclass(frozen=True)
class DarkKitchenAvailabilityQuery:
    """A request to check whether a dark kitchen serves a delivery area (COM-301).

    ``zip_code`` is the delivery postcode (validated at the HTTP edge); ``delivery_date`` is an
    optional target date. The check is not user-scoped — availability is a property of the area, not
    the caller — so no ``user_id`` is carried, though the endpoint still requires authentication.
    """

    zip_code: str
    delivery_date: date | None = None
