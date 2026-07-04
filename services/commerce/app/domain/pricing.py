"""Order pricing engine (COM-103).

Turns a plan's meals into *priced* order line items and computes the order totals
(``subtotal`` / ``deliveryFee`` / ``total``) in MXN. Everything here is pure domain logic — no
I/O — so it is fully unit-testable and deterministic.

**Where item prices come from.** The Dietary service carries no prices, so item pricing is owned
here: a :class:`PriceBook` port yields a per-serving unit price for a meal (keyed by meal type),
and ``line_total = unit_price * servings``.

**Delivery fees.** :class:`DeliveryFeeSchedule` maps each ``fulfillmentType`` to a flat fee, with an
optional free-delivery threshold (a subtotal at or above the threshold ships free). Pickup is free.

**Rounding.** All money is quantized to two decimals (centavos) with ``ROUND_HALF_UP`` by the
:class:`~app.domain.money.Money` value object. The engine rounds *per line* and the subtotal is the
sum of the already-rounded line totals ("round-then-sum"), so the displayed line items always
reconcile exactly to the subtotal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.enums import FulfillmentType
from app.domain.meal_plan import PlannedMeal
from app.domain.money import Money
from app.domain.order import Order, OrderItem


@runtime_checkable
class PriceBook(Protocol):
    """Resolves the per-serving unit price for a meal (by its meal type)."""

    def unit_price(self, meal_type: str) -> Money: ...


@dataclass(frozen=True)
class MealTypePriceBook:
    """A :class:`PriceBook` backed by a per-meal-type rate table with a default fallback.

    Lookups are case-insensitive; an unknown meal type falls back to ``default_rate``.
    """

    rates: Mapping[str, Money]
    default_rate: Money

    def unit_price(self, meal_type: str) -> Money:
        return self.rates.get(meal_type.strip().lower(), self.default_rate)


@dataclass(frozen=True)
class DeliveryFeeSchedule:
    """Per-``fulfillmentType`` delivery fees with an optional free-delivery threshold."""

    fees: Mapping[FulfillmentType, Money]
    free_delivery_threshold: Money | None = None

    def fee_for(self, fulfillment_type: FulfillmentType, subtotal: Money) -> Money:
        base = self.fees.get(fulfillment_type, Money.zero(subtotal.currency))
        threshold = self.free_delivery_threshold
        if (
            threshold is not None
            and base.amount > 0
            and subtotal.currency == threshold.currency
            and subtotal.amount >= threshold.amount
        ):
            return Money.zero(subtotal.currency)
        return base


def _display_name(meal: PlannedMeal) -> str:
    """Order-item name: the recipe name if the plan expanded it, else a label from the meal type."""
    return meal.recipe_name or meal.meal_type.replace("_", " ").title()


class OrderPricer:
    """Prices order line items and settles order totals (COM-103)."""

    def __init__(
        self,
        price_book: PriceBook,
        delivery_fees: DeliveryFeeSchedule,
        *,
        currency: str = "MXN",
    ) -> None:
        self._price_book = price_book
        self._delivery_fees = delivery_fees
        self._currency = currency

    def price_item(self, meal: PlannedMeal) -> OrderItem:
        """Project a planned meal onto a priced order line item."""
        unit_price = self._price_book.unit_price(meal.meal_type)
        return OrderItem(
            name=_display_name(meal),
            quantity=meal.servings,
            unit="serving",
            unit_price=unit_price,
            line_total=unit_price * meal.servings,
        )

    def price_order(self, order: Order) -> None:
        """Set ``subtotal``/``delivery_fee``/``total`` on the order from its (priced) items."""
        subtotal = self._sum_line_totals(order.items)
        delivery_fee = self._delivery_fees.fee_for(order.fulfillment_type, subtotal)
        order.subtotal = subtotal
        order.delivery_fee = delivery_fee
        order.total = subtotal + delivery_fee

    def _sum_line_totals(self, items: list[OrderItem]) -> Money:
        subtotal = Money.zero(self._currency)
        for item in items:
            subtotal = subtotal + item.line_total
        return subtotal
