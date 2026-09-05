"""Place a confirmed grocery order with its provider through the ACL (COM-408).

The first acceptance criterion of COM-408: once a grocery order is *confirmed*, it must actually be
placed with the provider the user chose. Confirmation happens in the same two places dark-kitchen
routing does (COM-303) -- inline when a card is charged at checkout (COM-202, via
:class:`~app.application.create_order.CreateOrderService`) and asynchronously when a provider
webhook settles an OXXO/SPEI/PayPal order (COM-206, via
:class:`~app.application.process_payment_webhook.ProcessPaymentWebhookService`) -- so both paths
call this one placer and the "confirmed -> placed" rule lives in a single, testable place.

Placement speaks only the COM-402 vocabulary, so nothing here knows which provider it is talking
to. It is deliberately narrow (only ``grocery_delivery`` orders that are actually ``confirmed`` and
not already placed) and, like kitchen routing, **best-effort**: it runs after the order is committed
and paid, so a provider outage must never turn a successful checkout into a ``500``. A failure is
logged and swallowed; the order simply stays unplaced and can be retried or reconciled later.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping

from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.grocery_catalog import (
    GroceryOrderLine,
    GroceryOrderRequest,
    GroceryProduct,
    GrocerySearchItem,
    GrocerySearchQuery,
)
from app.domain.order import Order, OrderItem
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher
from app.grocery.adapter import GroceryProviderAdapter

logger = logging.getLogger(__name__)


class GroceryOrderPlacer:
    """Places a just-confirmed grocery order with its provider (COM-408)."""

    def __init__(
        self,
        orders: OrderRepository,
        adapters: Mapping[str, GroceryProviderAdapter],
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._adapters = adapters
        self._publisher = publisher

    def place(self, order: Order) -> Order | None:
        """Place ``order`` with its grocery provider if it is ready for it (else a no-op).

        Skips anything that is not a confirmed ``grocery_delivery`` order, an order whose provider
        has no wired adapter, and -- crucially -- an order already placed, so a redelivered payment
        webhook can never buy the groceries twice. Any provider error is logged and swallowed.

        Returns the persisted order when a placement was recorded (so the caller can project the
        fresh state), otherwise ``None``.
        """
        if not self._is_placeable(order):
            return None
        adapter = self._adapters.get(str(order.provider_id))
        if adapter is None:
            logger.warning(
                "No grocery adapter wired for provider %s; order %s not placed",
                order.provider_id,
                order.id,
            )
            return None
        try:
            return self._place_with(order, adapter)
        except Exception:
            # Best-effort: the order is already committed and paid, so a provider outage must not
            # fail it. The order stays unplaced and is retried on the next sync/reconciliation.
            logger.exception(
                "Failed to place order %s with grocery provider %s", order.id, order.provider_id
            )
            return None

    def _is_placeable(self, order: Order) -> bool:
        return (
            order.fulfillment_type is FulfillmentType.GROCERY_DELIVERY
            and order.status is OrderStatus.CONFIRMED
            and order.provider_id is not None
            and not order.is_placed_with_provider
        )

    def _place_with(self, order: Order, adapter: GroceryProviderAdapter) -> Order | None:
        lines = self._resolve_lines(order, adapter)
        if not lines:
            logger.warning(
                "No purchasable products found for order %s at provider %s; not placed",
                order.id,
                order.provider_id,
            )
            return None
        placement = adapter.place_order(
            GroceryOrderRequest(
                provider_id=str(order.provider_id),
                reference=str(order.id),
                zip_code=order.delivery_address.zip_code,
                lines=lines,
            )
        )
        order.record_grocery_placement(
            external_order_id=placement.external_order_id, status=placement.status
        )
        persisted = self._orders.update(order)
        # A provider that accepts immediately can move the order on (e.g. straight to preparing);
        # publish any resulting transition once the placement is committed (COM-109).
        for event in order.pull_events():
            self._publisher.publish(event)
        return persisted

    def _resolve_lines(
        self, order: Order, adapter: GroceryProviderAdapter
    ) -> tuple[GroceryOrderLine, ...]:
        """Translate the order's items into provider order lines.

        An order line names an *ingredient* (it comes from a meal plan -- see COM-102), never a
        provider SKU, so the SKUs are resolved by asking the provider itself: one search carrying
        every item, then the first in-stock hit per matched ingredient. Items the provider cannot
        offer are dropped rather than blocking the whole order; a search that matches nothing at all
        leaves the order unplaced.
        """
        result = adapter.search(
            GrocerySearchQuery(
                zip_code=order.delivery_address.zip_code,
                items=tuple(
                    GrocerySearchItem(ingredient=item.name, quantity=item.quantity, unit=item.unit)
                    for item in order.items
                ),
                providers=(str(order.provider_id),),
            )
        )
        offers = self._offers_by_ingredient(result.products)
        lines: list[GroceryOrderLine] = []
        for item in order.items:
            product = offers.get(_normalise(item.name))
            if product is None:
                continue
            lines.append(GroceryOrderLine(sku=product.sku, quantity=_units_for(item)))
        return tuple(lines)

    @staticmethod
    def _offers_by_ingredient(
        products: tuple[GroceryProduct, ...],
    ) -> dict[str, GroceryProduct]:
        """Index the first in-stock hit per requested ingredient (out-of-stock hits are ignored)."""
        offers: dict[str, GroceryProduct] = {}
        for product in products:
            if not product.in_stock:
                continue
            key = _normalise(product.matched_ingredient or product.name)
            offers.setdefault(key, product)
        return offers


def _normalise(value: str) -> str:
    return value.strip().casefold()


def _units_for(item: OrderItem) -> int:
    """How many units of a product to buy for an order line.

    Order quantities are servings and may be fractional, while a provider sells whole units, so we
    round up -- buying a little extra is recoverable, buying too little is not. Every line buys at
    least one unit.
    """
    return max(1, math.ceil(item.quantity))
