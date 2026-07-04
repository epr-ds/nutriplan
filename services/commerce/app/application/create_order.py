"""COM-102/103 use case: create a priced order from a meal plan.

Orchestrates the anti-corruption boundary (fetch + ownership-check the plan via Dietary), turns the
plan's meals into *priced* order line items, computes the order totals, and persists a new PENDING
order scoped to the caller. Item pricing and the subtotal/deliveryFee/total math live in the
:class:`~app.domain.pricing.OrderPricer` domain service (COM-103).
"""

from __future__ import annotations

from app.application.commands import CreateOrderCommand
from app.application.ports import MealPlanProvider
from app.domain.enums import FulfillmentType
from app.domain.errors import MealPlanNotFoundError, OrderValidationError
from app.domain.order import Order
from app.domain.pricing import OrderPricer
from app.domain.repositories import OrderRepository


class CreateOrderService:
    """Creates priced orders from meal plans (COM-102 + COM-103)."""

    def __init__(
        self,
        orders: OrderRepository,
        meal_plans: MealPlanProvider,
        pricer: OrderPricer,
    ) -> None:
        self._orders = orders
        self._meal_plans = meal_plans
        self._pricer = pricer

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
            order.add_item(self._pricer.price_item(meal))
        self._pricer.price_order(order)

        return self._orders.add(order)
