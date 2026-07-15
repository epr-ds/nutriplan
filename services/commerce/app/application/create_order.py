"""COM-102/103 use case: create a priced order from a meal plan, charging a card inline (COM-202).

Orchestrates the anti-corruption boundary (fetch + ownership-check the plan via Dietary), turns the
plan's meals into *priced* order line items, computes the order totals, and persists a new order
scoped to the caller. Item pricing and the subtotal/deliveryFee/total math live in the
:class:`~app.domain.pricing.OrderPricer` domain service (COM-103).

When the request carries a **card** payment method (COM-202), the priced total is charged through
the :class:`~app.payments.provider.PaymentProvider` port using the provider-issued token -- so no
PAN ever reaches us. A successful charge confirms the order (``pending -> confirmed``) and records
the charge reference; a decline raises :class:`PaymentDeclinedError` (a ``402``) and nothing is
persisted. Non-card methods (or none) leave the order ``pending`` to settle asynchronously later.
"""

from __future__ import annotations

from app.application.commands import CreateOrderCommand
from app.application.ports import MealPlanProvider
from app.domain.enums import FulfillmentType
from app.domain.errors import MealPlanNotFoundError, OrderValidationError, PaymentDeclinedError
from app.domain.order import Order
from app.domain.payment import PaymentRequest
from app.domain.pricing import OrderPricer
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher
from app.payments.provider import PaymentProvider


class CreateOrderService:
    """Creates priced orders from meal plans (COM-102/103); charges cards inline (COM-202)."""

    def __init__(
        self,
        orders: OrderRepository,
        meal_plans: MealPlanProvider,
        pricer: OrderPricer,
        publisher: EventPublisher,
        payments: PaymentProvider,
    ) -> None:
        self._orders = orders
        self._meal_plans = meal_plans
        self._pricer = pricer
        self._publisher = publisher
        self._payments = payments

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
        order.record_created()
        # Charge before persisting so a decline leaves no order behind (COM-202); a successful
        # charge confirms the order and records the OrderStatusChanged event drained below.
        self._charge_card_if_requested(command, order)

        persisted = self._orders.add(order)
        # Publish after the order is committed; drain from the aggregate we built (the repository
        # may return a freshly rehydrated copy). Publishing is best-effort and never fails the
        # originating write.
        for event in order.pull_events():
            self._publisher.publish(event)
        return persisted

    def _charge_card_if_requested(self, command: CreateOrderCommand, order: Order) -> None:
        """Charge the order total when a card method is supplied; otherwise leave it pending.

        Only ``credit_card``/``debit_card`` settle inline here (COM-202); OXXO/SPEI/PayPal are
        confirmed asynchronously by their own stories, so those orders stay ``pending``. A declined
        charge raises :class:`PaymentDeclinedError` (a ``402``) so the caller can retry -- crucially
        *before* the order is persisted, so a failed payment never leaves an orphaned order.
        """
        method = command.payment_method_type
        if method is None or not method.is_card:
            return
        if not command.payment_token:
            raise OrderValidationError("a card payment method requires a token")

        result = self._payments.charge(
            PaymentRequest(
                amount=order.total,
                provider_token=command.payment_token,
                reference=str(order.id),
                description=f"NutriPlan order {order.id}",
            )
        )
        if not result.is_success:
            raise PaymentDeclinedError(
                error_code=result.error_code or "payment_failed",
                error_message=result.error_message,
            )
        order.mark_paid(provider=result.provider, charge_id=result.charge_id or "")
