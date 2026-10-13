"""Sync a placed grocery order's status back onto our own lifecycle (COM-408).

The second acceptance criterion of COM-408: the provider's fulfilment status must be reflected in
our order states. Grocery providers do not call us back (unlike payments in COM-206 or the kitchen
in COM-303), so the status is *pulled*: the caller asks us to refresh an order, we poll the provider
through the COM-402 ACL and apply the canonical status it reports.

Applying it is the domain's job (:meth:`~app.domain.order.Order.apply_grocery_status`), which walks
the lifecycle forward step by step, so a poll that skips several provider states still records every
intervening transition -- and a repeated or stale poll is an idempotent no-op that publishes
nothing.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.application.queries import SyncGroceryOrderQuery
from app.domain.errors import GroceryOrderNotPlacedError, OrderNotFoundError
from app.domain.order import Order
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher
from app.grocery.adapter import GroceryProviderAdapter


class SyncGroceryOrderStatusService:
    """Refreshes one order's status from its grocery provider (COM-408)."""

    def __init__(
        self,
        orders: OrderRepository,
        adapters: Mapping[str, GroceryProviderAdapter],
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._adapters = adapters
        self._publisher = publisher

    def sync(self, query: SyncGroceryOrderQuery) -> Order:
        """Poll the provider for ``query.order_id`` and apply the status it reports.

        Raises :class:`~app.domain.errors.OrderNotFoundError` when the order is unknown or not the
        caller's, :class:`~app.domain.errors.GroceryOrderNotPlacedError` when there is no provider
        order to poll, and :class:`~app.domain.errors.GroceryProviderUnavailableError` when the
        provider cannot answer -- here the caller *is* waiting on the provider, so unlike the
        best-effort placement the failure surfaces (as a ``503``) instead of being swallowed.
        """
        order = self._orders.get(query.order_id, user_id=query.user_id)
        if order is None:
            raise OrderNotFoundError(query.order_id)
        external_order_id = order.grocery_external_order_id
        if external_order_id is None:
            raise GroceryOrderNotPlacedError(order.id)
        adapter = self._adapters.get(str(order.provider_id))
        if adapter is None:
            raise GroceryOrderNotPlacedError(order.id)
        order.apply_grocery_status(adapter.get_order_status(external_order_id))
        persisted = self._orders.update(order)
        # Best-effort publish after the change is committed; an unchanged status recorded no events,
        # so a repeated sync publishes nothing (COM-109).
        for event in order.pull_events():
            self._publisher.publish(event)
        return persisted
