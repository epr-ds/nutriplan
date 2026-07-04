"""In-memory test doubles for the commerce use cases (no DB, no network)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.meal_plan import MealPlanSnapshot
from app.domain.money import Money
from app.domain.order import Order
from app.domain.pricing import DeliveryFeeSchedule, MealTypePriceBook, OrderPricer


def make_test_pricer() -> OrderPricer:
    """A real :class:`OrderPricer` with small, fixed rates for deterministic assertions.

    Rates (MXN per serving): breakfast 10, lunch 20, dinner 30, snack 5, default 15.
    Delivery fees: dark_kitchen 35, grocery_delivery 49, pickup 0. No free-delivery threshold
    (so the small subtotals in service/API tests never trip free delivery unexpectedly).
    """
    price_book = MealTypePriceBook(
        rates={
            "breakfast": Money(Decimal("10.00")),
            "lunch": Money(Decimal("20.00")),
            "dinner": Money(Decimal("30.00")),
            "snack": Money(Decimal("5.00")),
        },
        default_rate=Money(Decimal("15.00")),
    )
    delivery_fees = DeliveryFeeSchedule(
        fees={
            FulfillmentType.DARK_KITCHEN: Money(Decimal("35.00")),
            FulfillmentType.GROCERY_DELIVERY: Money(Decimal("49.00")),
            FulfillmentType.PICKUP: Money(Decimal("0.00")),
        },
    )
    return OrderPricer(price_book, delivery_fees)


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
