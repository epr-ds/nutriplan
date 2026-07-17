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

import uuid

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
    ) -> None:
        self._orders = orders
        self._payments = payments
        self._publisher = publisher

    def process(self, *, payload: bytes, signature: str) -> Order:
        # Verify + parse first: an untrusted or malformed event raises WebhookVerificationError
        # (a 400) before we touch any order.
        event = self._payments.parse_webhook(payload, signature)
        order = self._orders.get_by_id(_reference_to_id(event.reference))
        if order is None:
            raise OrderNotFoundError(event.reference)
        if event.type is PaymentEventType.CONFIRMED:
            order.confirm_payment(charge_id=event.charge_id)
        else:
            order.fail_payment()
        persisted = self._orders.update(order)
        # Best-effort publish after the settlement is committed; a redelivered webhook is an
        # idempotent no-op, so the aggregate recorded no events and nothing is published.
        for domain_event in order.pull_events():
            self._publisher.publish(domain_event)
        return persisted


def _reference_to_id(reference: str) -> uuid.UUID:
    """Map the provider's echoed reference back to an order id.

    The create-order flow hands the provider ``str(order.id)`` as the reference, so a well-formed
    webhook carries a UUID. A reference that is not a UUID cannot name any order of ours, so it is
    reported as a not-found order (a 404) rather than leaking that it was merely un-parseable.
    """
    try:
        return uuid.UUID(reference)
    except ValueError as exc:
        raise OrderNotFoundError(reference) from exc
