"""COM-605 use case: price an order for a meal plan without placing it.

The checkout's review step shows what the order will cost before anything is created or charged.
The plan is read through the same :class:`~app.application.ports.MealPlanProvider` the create use
case uses (the caller's token is forwarded, so Dietary enforces ownership), and priced by the same
:class:`~app.domain.pricing.OrderPricer`, so the quote matches the order the user then places.
Nothing is persisted, reserved or charged.
"""

from __future__ import annotations

from app.application.ports import MealPlanProvider
from app.application.queries import QuoteOrderQuery
from app.domain.enums import FulfillmentType
from app.domain.errors import MealPlanNotFoundError, OrderValidationError
from app.domain.pricing import OrderPricer, PriceQuote


class QuoteOrderService:
    """Prices an order for one of the caller's meal plans (COM-605)."""

    def __init__(self, meal_plans: MealPlanProvider, pricer: OrderPricer) -> None:
        self._meal_plans = meal_plans
        self._pricer = pricer

    def quote(self, query: QuoteOrderQuery, *, bearer_token: str) -> PriceQuote:
        if query.fulfillment_type is FulfillmentType.GROCERY_DELIVERY and not query.provider_id:
            raise OrderValidationError("providerId is required for grocery_delivery orders")
        snapshot = self._meal_plans.fetch(query.meal_plan_id, bearer_token=bearer_token)
        if snapshot is None:
            raise MealPlanNotFoundError(query.meal_plan_id)
        return self._pricer.quote(snapshot.meals, query.fulfillment_type)
