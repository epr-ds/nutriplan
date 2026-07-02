"""In-memory test doubles for the commerce use cases (no DB, no network)."""

from __future__ import annotations

import uuid
from datetime import date

from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.enums import OrderStatus
from app.domain.meal_plan import MealPlanSnapshot
from app.domain.order import Order


class InMemoryOrderRepository:
    """Satisfies the ``OrderRepository`` port with a dict, preserving owner-scoping semantics."""

    def __init__(self) -> None:
        self.orders: dict[uuid.UUID, Order] = {}

    def add(self, order: Order) -> Order:
        self.orders[order.id] = order
        return order

    def get(self, order_id: uuid.UUID, *, user_id: uuid.UUID) -> Order | None:
        order = self.orders.get(order_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        from_date: date | None = None,
    ) -> list[Order]:
        return [o for o in self.orders.values() if o.user_id == user_id]


class FakeMealPlanProvider:
    """Returns a preset snapshot (or ``None``) and records how it was called."""

    def __init__(self, snapshot: MealPlanSnapshot | None) -> None:
        self._snapshot = snapshot
        self.calls: list[tuple[str, str]] = []

    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None:
        self.calls.append((plan_id, bearer_token))
        return self._snapshot


class StubVerifier:
    """Maps known tokens to principals; anything else is an invalid token."""

    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc
