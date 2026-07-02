"""COM-102 use case: create an order from a meal plan.

Orchestrates the anti-corruption boundary (fetch + ownership-check the plan via Dietary), turns the
plan's meals into order line items, and persists a new PENDING order scoped to the caller. Line
items and totals start at zero here — the pricing engine (COM-103) fills them in next.
"""

from __future__ import annotations

from app.application.commands import CreateOrderCommand
from app.application.ports import MealPlanProvider
from app.domain.enums import FulfillmentType
from app.domain.errors import MealPlanNotFoundError, OrderValidationError
from app.domain.meal_plan import PlannedMeal
from app.domain.money import Money
from app.domain.order import Order, OrderItem
from app.domain.repositories import OrderRepository


def _meal_to_item(meal: PlannedMeal) -> OrderItem:
    """Project a planned meal onto an (as-yet unpriced) order line item."""
    name = meal.recipe_name or meal.meal_type.replace("_", " ").title()
    return OrderItem(
        name=name,
        quantity=meal.servings,
        unit="serving",
        unit_price=Money.zero(),
        line_total=Money.zero(),
    )


class CreateOrderService:
    """Creates orders from meal plans (COM-102)."""

    def __init__(self, orders: OrderRepository, meal_plans: MealPlanProvider) -> None:
        self._orders = orders
        self._meal_plans = meal_plans

    def create(self, command: CreateOrderCommand, *, bearer_token: str) -> Order:
        if command.fulfillment_type is FulfillmentType.GROCERY_DELIVERY and not command.provider_id:
            raise OrderValidationError("providerId is required for grocery_delivery orders")

        snapshot = self._meal_plans.fetch(command.meal_plan_id, bearer_token=bearer_token)
        if snapshot is None:
            raise MealPlanNotFoundError(command.meal_plan_id)

        order = Order(
            user_id=command.user_id,
            fulfillment_type=command.fulfillment_type,
            delivery_address=command.delivery_address,
            delivery_date=command.delivery_date,
            delivery_time_slot=command.delivery_time_slot,
            provider_id=command.provider_id,
            notes=command.notes,
        )
        for meal in snapshot.meals:
            order.add_item(_meal_to_item(meal))

        return self._orders.add(order)
