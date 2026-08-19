"""COM-303 use case: advance an order from a verified kitchen status webhook.

The inbound half of dark-kitchen fulfilment. A kitchen reports progress by POSTing a signed
callback; this thin write-side application service verifies it through the
:class:`~app.adapters.kitchen_webhook_verifier.KitchenWebhookVerifier` (so signature verification
stays out of the transport layer), loads the referenced order **by id alone** -- the webhook is
authenticated by its signature, not a user token, so the lookup is deliberately not owner-scoped --
and applies the :class:`~app.domain.kitchen.KitchenEventType` to the order's lifecycle:
``kitchen.preparing`` -> :meth:`Order.report_preparing`, ``kitchen.dispatched`` ->
:meth:`Order.report_dispatched`. Both are idempotent, so a redelivered webhook is a safe no-op that
records (and publishes) nothing; an out-of-order report (dispatch before preparing, a report for a
cancelled order) raises :class:`~app.domain.errors.IllegalOrderTransitionError` (a 409).
"""

from __future__ import annotations

from app.adapters.kitchen_webhook_verifier import KitchenWebhookVerifier
from app.application.webhook_references import reference_to_order_id
from app.domain.errors import OrderNotFoundError
from app.domain.kitchen import KitchenEventType
from app.domain.order import Order
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher


class ProcessKitchenWebhookService:
    """Advances an order's fulfilment state from a verified kitchen webhook (COM-303).

    On a state change it publishes the resulting ``order.status_changed`` event to the bus
    (COM-109); a redelivered (idempotent) webhook changes nothing and publishes nothing.
    """

    def __init__(
        self,
        orders: OrderRepository,
        verifier: KitchenWebhookVerifier,
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._verifier = verifier
        self._publisher = publisher

    def process(self, *, payload: bytes, signature: str) -> Order:
        # Verify + parse first: an untrusted or malformed event raises WebhookVerificationError
        # (a 400) before we touch any order.
        event = self._verifier.parse(payload, signature)
        order = self._orders.get_by_id(reference_to_order_id(event.reference))
        if order is None:
            raise OrderNotFoundError(event.reference)
        if event.type is KitchenEventType.PREPARING:
            order.report_preparing()
        else:
            order.report_dispatched()
        persisted = self._orders.update(order)
        # Best-effort publish after the change is committed; a redelivered webhook is an idempotent
        # no-op, so the aggregate recorded no events and nothing is published.
        for domain_event in order.pull_events():
            self._publisher.publish(domain_event)
        return persisted
