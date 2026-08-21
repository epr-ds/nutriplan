"""FreshBasket grocery provider adapter (COM-404) -- a real HTTP ``GroceryProviderAdapter``.

The first concrete grocery adapter behind the COM-402 anti-corruption layer. It speaks FreshBasket's
own sandbox REST API (its JSON request/response shapes and fulfilment status strings) and translates
everything to and from the provider-agnostic vocabulary in :mod:`app.domain.grocery_catalog`, so no
FreshBasket wire type, status string, or field name ever crosses the seam. A synchronous
``httpx.Client`` keeps the whole request path consistent with the service's sync stack, and a
``transport`` can be injected so the mapping is unit-testable without a live FreshBasket.

Every transport or upstream failure (a connection error, a non-2xx response, or an unparsable body)
is normalised to :class:`~app.domain.errors.GroceryProviderUnavailableError`, so the fan-out search
(COM-403) can skip a flaky provider and COM-407 can layer per-provider circuit breakers over it.
Sandbox credentials are injected via configuration (COM-905): an empty key makes the factory fall
back to the in-process fake, so dev/CI needs no secret.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery_catalog import (
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GroceryProduct,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.domain.money import Money

_PROVIDER_ID = "freshbasket"

# FreshBasket's own fulfilment vocabulary -> our canonical lifecycle. An unrecognised value maps to
# UNKNOWN (for a status poll) or PENDING (for a fresh placement) so the raw provider string never
# leaks past the ACL.
_STATUS_MAP: dict[str, GroceryOrderStatus] = {
    "created": GroceryOrderStatus.PENDING,
    "confirmed": GroceryOrderStatus.CONFIRMED,
    "picking": GroceryOrderStatus.PREPARING,
    "en_route": GroceryOrderStatus.OUT_FOR_DELIVERY,
    "delivered": GroceryOrderStatus.DELIVERED,
    "cancelled": GroceryOrderStatus.CANCELLED,
    "failed": GroceryOrderStatus.FAILED,
}


def _money_from_cents(cents: object, currency: object) -> Money:
    """Translate FreshBasket's integer minor units + currency into domain :class:`Money`."""
    try:
        amount = Decimal(str(cents)) / 100
    except (InvalidOperation, TypeError):
        amount = Decimal(0)
    return Money(amount, str(currency) if currency else "MXN")


class FreshBasketGroceryAdapter:
    """Searches, orders, and reports status against FreshBasket's sandbox REST API (COM-404)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        provider_id: str = _PROVIDER_ID,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._provider_id = provider_id
        self._timeout = timeout
        self._transport = transport

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        body = {
            "postalCode": query.zip_code,
            "items": [item.ingredient for item in query.items],
        }
        payload = self._post("/catalog/search", body)
        products = tuple(
            self._to_product(raw) for raw in payload.get("results") or [] if isinstance(raw, dict)
        )
        return GrocerySearchResult(provider_id=self._provider_id, products=products)

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        body = {
            "reference": request.reference,
            "postalCode": request.zip_code,
            "lines": [{"sku": line.sku, "quantity": line.quantity} for line in request.lines],
        }
        payload = self._post("/orders", body)
        status = _STATUS_MAP.get(str(payload.get("status", "")), GroceryOrderStatus.PENDING)
        return GroceryOrderPlacement(
            provider_id=self._provider_id,
            external_order_id=str(payload.get("orderId", "")),
            status=status,
            total=self._to_money(payload.get("total")),
        )

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        payload = self._get(f"/orders/{external_order_id}")
        return _STATUS_MAP.get(str(payload.get("status", "")), GroceryOrderStatus.UNKNOWN)

    # -- HTTP plumbing -----------------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._client() as client:
                response = client.post(f"{self._base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            raise GroceryProviderUnavailableError(self._provider_id, str(exc)) from exc
        return self._parse(response)

    def _get(self, path: str) -> dict[str, Any]:
        try:
            with self._client() as client:
                response = client.get(f"{self._base_url}{path}")
        except httpx.HTTPError as exc:
            raise GroceryProviderUnavailableError(self._provider_id, str(exc)) from exc
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        if not response.is_success:
            raise GroceryProviderUnavailableError(self._provider_id, f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GroceryProviderUnavailableError(
                self._provider_id, "non-JSON response body"
            ) from exc
        return payload if isinstance(payload, dict) else {}

    # -- mapping -----------------------------------------------------------------------------------

    def _to_product(self, raw: dict[str, Any]) -> GroceryProduct:
        """Translate one FreshBasket catalogue hit into a domain :class:`GroceryProduct`."""
        unit = raw.get("unit")
        ingredient = raw.get("ingredient")
        return GroceryProduct(
            provider_id=self._provider_id,
            sku=str(raw.get("sku", "")),
            name=str(raw.get("name", "")),
            price=_money_from_cents(raw.get("priceCents"), raw.get("currency")),
            unit=unit if isinstance(unit, str) else None,
            in_stock=raw.get("availability") == "available",
            matched_ingredient=ingredient if isinstance(ingredient, str) else None,
        )

    @staticmethod
    def _to_money(total: object) -> Money | None:
        """Translate an optional FreshBasket ``{amountCents, currency}`` object into ``Money``."""
        if not isinstance(total, dict):
            return None
        return _money_from_cents(total.get("amountCents"), total.get("currency"))
