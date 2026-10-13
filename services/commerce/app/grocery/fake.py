"""An in-process fake grocery provider adapter for dev, CI, and tests (COM-402).

It backs the :class:`~app.grocery.adapter.GroceryProviderAdapter` seam without a real provider or
network, and deliberately *speaks a provider-shaped wire format internally* -- a raw catalogue of
dicts with provider-ish keys (``id``, ``title``, ``price_cents``, ``currency``, ``availability``)
and provider status strings -- so that mapping those to domain value objects exercises the very
anti-corruption boundary this story is about. Everything it returns is domain vocabulary
(:mod:`app.domain.grocery_catalog`); no dict or provider string ever escapes.

``search`` matches the query's ingredients against the catalogue; ``place_order`` mints a
deterministic ``external_order_id``, records the request (in :attr:`orders`) and returns a
``PENDING`` placement; ``get_order_status`` maps a provider status string onto the canonical
:class:`~app.domain.grocery_catalog.GroceryOrderStatus` (an unknown string -> ``UNKNOWN``).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.domain.grocery_catalog import (
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GroceryProduct,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.domain.money import Money

# A provider-shaped catalogue keyed by ingredient: exactly the kind of raw payload a real provider
# returns, kept here so the fake has something to *translate* across the ACL rather than storing
# domain objects directly.
_DEFAULT_CATALOGUE: dict[str, list[dict[str, object]]] = {
    "milk": [
        {
            "id": "fb-milk-1l",
            "title": "Whole Milk 1L",
            "price_cents": 2450,
            "currency": "MXN",
            "unit": "1 L",
            "availability": "in_stock",
        },
    ],
    "eggs": [
        {
            "id": "fb-eggs-12",
            "title": "Free-Range Eggs (12)",
            "price_cents": 5490,
            "currency": "MXN",
            "unit": "dozen",
            "availability": "in_stock",
        },
    ],
    "bread": [
        {
            "id": "fb-bread-wg",
            "title": "Whole-Grain Bread",
            "price_cents": 3200,
            "currency": "MXN",
            "unit": "680 g",
            "availability": "out_of_stock",
        },
    ],
}

# Provider status vocabulary -> our canonical lifecycle. Unknown strings fall back to UNKNOWN so the
# raw provider value never leaks past the ACL.
_STATUS_MAP: dict[str, GroceryOrderStatus] = {
    "created": GroceryOrderStatus.PENDING,
    "accepted": GroceryOrderStatus.CONFIRMED,
    "picking": GroceryOrderStatus.PREPARING,
    "dispatched": GroceryOrderStatus.OUT_FOR_DELIVERY,
    "delivered": GroceryOrderStatus.DELIVERED,
    "canceled": GroceryOrderStatus.CANCELLED,
    "rejected": GroceryOrderStatus.FAILED,
}


class FakeGroceryProviderAdapter:
    """A deterministic in-memory :class:`GroceryProviderAdapter` for dev/CI and tests."""

    def __init__(
        self,
        provider_id: str = "fake",
        *,
        catalogue: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._catalogue = catalogue if catalogue is not None else _DEFAULT_CATALOGUE
        self.orders: list[GroceryOrderRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        products: list[GroceryProduct] = []
        for item in query.items:
            for raw in self._catalogue.get(item.ingredient.strip().lower(), ()):
                products.append(self._to_product(raw, matched=item.ingredient))
        return GrocerySearchResult(provider_id=self._provider_id, products=tuple(products))

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        self.orders.append(request)
        return GroceryOrderPlacement(
            provider_id=self._provider_id,
            external_order_id=f"{self._provider_id}_ord_{uuid.uuid4().hex[:12]}",
            status=GroceryOrderStatus.PENDING,
        )

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        # A real adapter polls the provider; the fake reads a provider status from an optional
        # ``:<status>`` suffix on the id (a freshly minted id has none -> "created" -> PENDING) so
        # tests can drive the mapping through the real port method.
        raw_status = external_order_id.rsplit(":", 1)[-1] if ":" in external_order_id else "created"
        return _STATUS_MAP.get(raw_status, GroceryOrderStatus.UNKNOWN)

    def _to_product(self, raw: Mapping[str, object], *, matched: str) -> GroceryProduct:
        """Translate one provider-shaped catalogue entry into a domain :class:`GroceryProduct`."""
        price = Money(Decimal(str(raw["price_cents"])) / 100, str(raw.get("currency", "MXN")))
        unit = raw.get("unit")
        return GroceryProduct(
            provider_id=self._provider_id,
            sku=str(raw["id"]),
            name=str(raw["title"]),
            price=price,
            unit=unit if isinstance(unit, str) else None,
            in_stock=raw.get("availability") == "in_stock",
            matched_ingredient=matched,
        )
