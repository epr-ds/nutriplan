"""COM-206 use case: settle an order from a verified provider payment webhook.

An asynchronous method (OXXO voucher COM-203 / SPEI transfer COM-204) leaves the order ``pending``
at checkout; the provider later posts a signed webhook once the customer pays (or fails to). This
thin write-side application service verifies that webhook through the
:class:`~app.payments.provider.PaymentProvider` port (so signature verification stays
provider-specific and out of the transport layer), loads the referenced order **by id alone** -- the
webhook is authenticated by its signature, not a user token, so the lookup is deliberately not
owner-scoped -- and drives the order to its settled state: :meth:`Order.confirm_payment` on success
or :meth:`Order.fail_payment` on failure. Both are idempotent, so a redelivered webhook is a safe
no-op that records (and publishes) nothing.
"""

from __future__ import annotations

from app.application.place_grocery_order import GroceryOrderPlacer
from app.application.reserve_slot import ReserveDeliverySlotService
from app.application.route_to_kitchen import KitchenRouter
from app.application.webhook_references import reference_to_order_id
from app.domain.errors import OrderNotFoundError
from app.domain.order import Order
from app.domain.payment import PaymentEventType
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher
from app.payments.provider import PaymentProvider


class ProcessPaymentWebhookService:
    """Settles an order from a verified provider payment webhook (COM-206).

    On a state change it publishes the resulting ``order.status_changed`` event to the bus
    (COM-109); a redelivered (idempotent) webhook changes nothing and publishes nothing.
    """

    def __init__(
        self,
        orders: OrderRepository,
        payments: PaymentProvider,
        publisher: EventPublisher,
        kitchen_router: KitchenRouter | None = None,
        slot_reservations: ReserveDeliverySlotService | None = None,
        grocery_placer: GroceryOrderPlacer | None = None,
    ) -> None:
        self._orders = orders
        self._payments = payments
        self._publisher = publisher
        self._kitchen_router = kitchen_router
        self._slot_reservations = slot_reservations
        self._grocery_placer = grocery_placer

    def process(self, *, payload: bytes, signature: str) -> Order:
        # Verify + parse first: an untrusted or malformed event raises WebhookVerificationError
        # (a 400) before we touch any order.
        event = self._payments.parse_webhook(payload, signature)
        order = self._orders.get_by_id(reference_to_order_id(event.reference))
        if order is None:
            raise OrderNotFoundError(event.reference)
        if event.type is PaymentEventType.CONFIRMED:
            order.confirm_payment(charge_id=event.charge_id)
        else:
            order.fail_payment()
            # A failed async payment cancels the order (pending -> cancelled), so release any
            # dark-kitchen slot it held to free the capacity (COM-304). Idempotent: a redelivered
            # failure changes no state above and re-releasing an already-freed slot is a no-op.
            if self._slot_reservations is not None:
                self._slot_reservations.release_for(order.id)
        persisted = self._orders.update(order)
        # Best-effort publish after the settlement is committed; a redelivered webhook is an
        # idempotent no-op, so the aggregate recorded no events and nothing is published.
        for domain_event in order.pull_events():
            self._publisher.publish(domain_event)
        # Route a now-confirmed dark-kitchen order to the kitchen (COM-303). Best-effort and a
        # no-op unless this webhook actually confirmed a dark-kitchen order (a failure or
        # redelivery skips it).
        if self._kitchen_router is not None:
            self._kitchen_router.route(order)
        # Place a now-confirmed grocery order with its provider (COM-408). Best-effort and a no-op
        # unless this webhook actually confirmed a grocery order; already-placed orders are skipped,
        # so a redelivered confirmation never orders the groceries twice.
        if self._grocery_placer is not None:
            placed = self._grocery_placer.place(order)
            if placed is not None:
                persisted = placed
        return persisted
