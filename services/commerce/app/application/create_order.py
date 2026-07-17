"""COM-102/103 use case: create a priced order from a meal plan, charging a card inline (COM-202).

Orchestrates the anti-corruption boundary (fetch + ownership-check the plan via Dietary), turns the
plan's meals into *priced* order line items, computes the order totals, and persists a new order
scoped to the caller. Item pricing and the subtotal/deliveryFee/total math live in the
:class:`~app.domain.pricing.OrderPricer` domain service (COM-103).

When the request carries a **card** payment method (COM-202), the priced total is charged through
the :class:`~app.payments.provider.PaymentProvider` port using the provider-issued token -- so no
PAN ever reaches us. A successful charge confirms the order (``pending -> confirmed``) and records
the charge reference; a decline raises :class:`PaymentDeclinedError` (a ``402``) and nothing is
persisted. An **OXXO** request instead issues a voucher through the same port (COM-203) and leaves
the order ``pending`` -- the customer pays it later and a webhook confirms settlement (COM-206).
Other async methods (or none) also leave the order ``pending``.

A client may pass an ``Idempotency-Key`` (COM-209): the first successful create is recorded so a
retry carrying the same key *replays* the original order instead of creating — or charging — a
second time, and the key is forwarded to the provider so the charge itself is de-duplicated too. A
key reused with a *different* request body is rejected as a :class:`IdempotencyConflictError`.
"""

from __future__ import annotations

import hashlib
import json

from app.application.commands import CreateOrderCommand
from app.application.idempotency import IdempotencyStore
from app.application.ports import MealPlanProvider
from app.domain.enums import FulfillmentType, PaymentMethodType
from app.domain.errors import (
    IdempotencyConflictError,
    MealPlanNotFoundError,
    OrderValidationError,
    PaymentDeclinedError,
)
from app.domain.order import Order
from app.domain.payment import PaymentRequest, PaymentVoucherRequest
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
        idempotency: IdempotencyStore,
    ) -> None:
        self._orders = orders
        self._meal_plans = meal_plans
        self._pricer = pricer
        self._publisher = publisher
        self._payments = payments
        self._idempotency = idempotency

    def create(
        self,
        command: CreateOrderCommand,
        *,
        bearer_token: str,
        idempotency_key: str | None = None,
    ) -> Order:
        fingerprint = _fingerprint(command) if idempotency_key is not None else None
        if idempotency_key is not None:
            replay = self._replay(command, key=idempotency_key, fingerprint=fingerprint or "")
            if replay is not None:
                return replay

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
        # Settle payment before persisting so a decline leaves no order behind (COM-202); a
        # successful card charge confirms the order, while an OXXO voucher (COM-203) leaves it
        # pending. Either records the events drained below.
        self._settle_payment(command, order, idempotency_key=idempotency_key)

        persisted = self._orders.add(order)
        # Record the key only after a successful create, so a declined/invalid request leaves no
        # key behind and can be retried (COM-209). Stored in the same request session as the order.
        if idempotency_key is not None:
            self._idempotency.save(
                idempotency_key,
                user_id=command.user_id,
                order_id=persisted.id,
                request_fingerprint=fingerprint or "",
            )
        # Publish after the order is committed; drain from the aggregate we built (the repository
        # may return a freshly rehydrated copy). Publishing is best-effort and never fails the
        # originating write.
        for event in order.pull_events():
            self._publisher.publish(event)
        return persisted

    def _replay(self, command: CreateOrderCommand, *, key: str, fingerprint: str) -> Order | None:
        """Return the order a prior request with this key produced, or ``None`` if the key is new.

        A key already on file that was used for a *different* request (fingerprint mismatch) is a
        client error → :class:`IdempotencyConflictError`. Otherwise we reload and return the
        original order, so the retry gets an identical result without creating or charging again.
        """
        existing = self._idempotency.find(key, user_id=command.user_id)
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(key)
        order = self._orders.get(existing.order_id, user_id=command.user_id)
        if order is None:
            # A key is only recorded after its order is committed and orders are never deleted, so
            # this is unreachable in practice; refuse rather than silently re-create/charge.
            raise IdempotencyConflictError(key)
        return order

    def _settle_payment(
        self, command: CreateOrderCommand, order: Order, *, idempotency_key: str | None
    ) -> None:
        """Route the requested payment method to its settlement path (or leave the order pending).

        Cards (``credit_card``/``debit_card``) charge inline and confirm the order (COM-202); OXXO
        issues a voucher and leaves the order ``pending`` until a webhook confirms it (COM-203);
        SPEI/PayPal and no method also stay ``pending``, settled by their own later stories. Any
        ``idempotency_key`` is threaded through so the provider de-duplicates a retried request.
        """
        method = command.payment_method_type
        if method is None:
            return
        if method.is_card:
            self._charge_card(command, order, idempotency_key=idempotency_key)
        elif method is PaymentMethodType.OXXO:
            self._issue_oxxo_voucher(order, idempotency_key=idempotency_key)

    def _charge_card(
        self, command: CreateOrderCommand, order: Order, *, idempotency_key: str | None
    ) -> None:
        """Charge the order total against the supplied card token and confirm the order (COM-202).

        A declined charge raises :class:`PaymentDeclinedError` (a ``402``) so the caller can
        retry -- crucially *before* the order is persisted, so a failed payment never leaves an
        orphaned order. Any ``idempotency_key`` is forwarded so the provider de-duplicates the
        charge too (COM-209).
        """
        if not command.payment_token:
            raise OrderValidationError("a card payment method requires a token")

        result = self._payments.charge(
            PaymentRequest(
                amount=order.total,
                provider_token=command.payment_token,
                reference=str(order.id),
                description=f"NutriPlan order {order.id}",
                idempotency_key=idempotency_key,
            )
        )
        if not result.is_success:
            raise PaymentDeclinedError(
                error_code=result.error_code or "payment_failed",
                error_message=result.error_message,
            )
        order.mark_paid(provider=result.provider, charge_id=result.charge_id or "")

    def _issue_oxxo_voucher(self, order: Order, *, idempotency_key: str | None) -> None:
        """Issue an OXXO voucher for the order total, leaving the order ``pending`` (COM-203).

        The provider mints a reference (and barcode) the customer pays at an OXXO store; the order
        stays ``pending`` until settlement is confirmed asynchronously by a webhook (COM-206). No
        card token is involved -- there is nothing to charge yet. Any ``idempotency_key`` is
        forwarded so a retried create re-issues the *same* voucher, not a duplicate (COM-209).
        """
        voucher = self._payments.create_voucher(
            PaymentVoucherRequest(
                amount=order.total,
                reference=str(order.id),
                description=f"NutriPlan order {order.id}",
                idempotency_key=idempotency_key,
            )
        )
        order.attach_voucher(
            provider=voucher.provider,
            reference=voucher.reference,
            expires_at=voucher.expires_at,
            barcode_url=voucher.barcode_url,
        )


def _fingerprint(command: CreateOrderCommand) -> str:
    """A stable hash of the *semantic* create-order request, to detect a reused Idempotency-Key.

    The delivery address' surrogate ``id``/``user_id`` (freshly generated per request) are excluded
    so two byte-identical requests hash identically, while any meaningful difference (a different
    plan, address, date, or payment token) changes the digest and surfaces as a ``409``.
    """
    address = command.delivery_address
    payload = {
        "user_id": str(command.user_id),
        "meal_plan_id": command.meal_plan_id,
        "fulfillment_type": command.fulfillment_type.value,
        "provider_id": command.provider_id,
        "delivery_date": command.delivery_date.isoformat(),
        "delivery_time_slot": command.delivery_time_slot,
        "notes": command.notes,
        "payment_method_type": (
            command.payment_method_type.value if command.payment_method_type else None
        ),
        "payment_token": command.payment_token,
        "address": {
            "street": address.street,
            "apartment": address.apartment,
            "city": address.city,
            "state": address.state,
            "zip_code": address.zip_code,
            "country": address.country,
            "instructions": address.instructions,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
