"""Route a confirmed dark-kitchen order to a kitchen queue (COM-303).

The first acceptance criterion of COM-303: once an order is *confirmed*, a dark-kitchen order must
reach a kitchen. Confirmation happens in two places -- inline when a card is charged at checkout
(COM-202, via :class:`~app.application.create_order.CreateOrderService`) and asynchronously when a
provider webhook settles an OXXO/SPEI/PayPal order (COM-206, via
:class:`~app.application.process_payment_webhook.ProcessPaymentWebhookService`). Both paths call
this one router after the order is committed, so the "confirmed -> routed" rule lives in a single,
testable place regardless of how the order was paid.

Routing is deliberately narrow (only dark-kitchen orders that are actually ``confirmed``) and
best-effort: it runs after the write is durable, so a kitchen-queue outage must never turn a
successful order into a ``500`` -- the failure is logged and swallowed, exactly as domain-event
publishing is (COM-109).
"""

from __future__ import annotations

import logging

from app.application.ports import KitchenQueue
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.kitchen import KitchenTicket
from app.domain.order import Order

logger = logging.getLogger(__name__)


class KitchenRouter:
    """Hands a just-confirmed dark-kitchen order to the kitchen queue (COM-303)."""

    def __init__(self, queue: KitchenQueue) -> None:
        self._queue = queue

    def route(self, order: Order) -> None:
        """Route ``order`` to the kitchen if it is a confirmed dark-kitchen order (else a no-op).

        Only dark-kitchen orders in the ``confirmed`` state are routed: a grocery/pickup order, or a
        dark-kitchen order still ``pending`` (an unsettled async payment) or already further along,
        is skipped. Any error from the queue is logged and swallowed so a committed order is never
        failed by a routing hiccup.
        """
        if order.fulfillment_type is not FulfillmentType.DARK_KITCHEN:
            return
        if order.status is not OrderStatus.CONFIRMED:
            return
        try:
            self._queue.route(KitchenTicket.for_order(order))
        except Exception:
            # Best-effort: the order is already committed, so a kitchen-queue outage must not fail
            # it. A future kitchen consumer can also reconcile from the order.confirmed bus event.
            logger.exception("Failed to route order %s to the kitchen queue", order.id)
