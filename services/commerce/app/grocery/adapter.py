"""The grocery provider port -- the anti-corruption boundary around a delivery provider (COM-402).

The application layer depends only on this small surface: given provider-agnostic value objects it
searches a provider's catalogue, places an order, and reports an order's status, returning only
domain vocabulary (:mod:`app.domain.grocery_catalog`). Keeping it a port lets FreshBasket (COM-404),
Walmart (COM-405) and Chedraui (COM-406) be interchangeable adapters -- each translating its own
JSON/SDK shapes to and from these types -- while an in-process fake backs dev/CI and tests. No
provider wire type, status string, or SDK object ever crosses this seam.

Transport/upstream failures normalise to :class:`~app.domain.errors.GroceryProviderUnavailableError`
so a flaky provider is a domain condition the caller can handle (COM-407 wraps this in per-provider
circuit breakers, timeouts, and fallback).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.grocery_catalog import (
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GrocerySearchQuery,
    GrocerySearchResult,
)


@runtime_checkable
class GroceryProviderAdapter(Protocol):
    """Searches, orders, and reports status for one grocery provider, provider-agnostically."""

    @property
    def provider_id(self) -> str:
        """The stable id of the backing provider (matches its ``GroceryProvider.id``)."""
        ...

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        """Return the provider's matches for ``query`` as normalised domain products."""
        ...

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        """Place ``request`` and report the provider order id plus canonical status."""
        ...

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        """Map the provider's current status for ``external_order_id`` onto the canonical set."""
        ...
