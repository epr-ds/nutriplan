"""Walmart grocery provider adapter (COM-405) -- the second real ``GroceryProviderAdapter``.

A fast-follow behind FreshBasket (COM-404): another concrete adapter behind the COM-402
anti-corruption layer, deliberately speaking Walmart's *own* sandbox REST dialect so the ACL earns
its keep. Walmart differs from FreshBasket on every axis the boundary has to absorb -- a
``WM_SEC.ACCESS_TOKEN`` auth header (not bearer), decimal-currency prices (``salePrice`` /
``orderTotal.amount``, not integer cents), TitleCase fulfilment statuses, and its own field names --
and none of it leaks: everything is translated to and from the provider-agnostic vocabulary in
:mod:`app.domain.grocery_catalog`.

A synchronous ``httpx.Client`` keeps the request path consistent with the service's sync stack, and
a ``transport`` can be injected so the mapping is unit-testable without a live Walmart. Every
transport or upstream failure (a connection error, a non-2xx response, or an unparsable body) is
normalised to :class:`~app.domain.errors.GroceryProviderUnavailableError`, so the fan-out search
(COM-403) can skip a flaky provider and COM-407 can layer per-provider circuit breakers over it.
Sandbox credentials are injected via configuration: an empty key makes the factory fall back to the
in-process fake, so dev/CI needs no secret.
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

_PROVIDER_ID = "walmart"

# Walmart's own fulfilment vocabulary (TitleCase on the wire) -> our canonical lifecycle. Matched
# case-insensitively; an unrecognised value maps to UNKNOWN (for a status poll) or PENDING (for a
# fresh placement) so the raw provider string never leaks past the ACL.
_STATUS_MAP: dict[str, GroceryOrderStatus] = {
    "created": GroceryOrderStatus.PENDING,
    "acknowledged": GroceryOrderStatus.CONFIRMED,
    "preparing": GroceryOrderStatus.PREPARING,
    "shipped": GroceryOrderStatus.OUT_FOR_DELIVERY,
    "delivered": GroceryOrderStatus.DELIVERED,
    "cancelled": GroceryOrderStatus.CANCELLED,
    "failed": GroceryOrderStatus.FAILED,
}


def _money_from_amount(amount: object, currency: object) -> Money:
    """Translate Walmart's decimal currency amount + code into domain :class:`Money`."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        value = Decimal(0)
    return Money(value, str(currency) if currency else "MXN")


class WalmartGroceryAdapter:
    """Searches, orders, and reports status against Walmart's sandbox REST API (COM-405)."""

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
            "searchTerms": [item.ingredient for item in query.items],
            "shipToPostalCode": query.zip_code,
        }
        payload = self._post("/items/search", body)
        products = tuple(
            self._to_product(raw) for raw in payload.get("items") or [] if isinstance(raw, dict)
        )
        return GrocerySearchResult(provider_id=self._provider_id, products=products)

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        body = {
            "purchaseOrderId": request.reference,
            "shipToPostalCode": request.zip_code,
            "orderLines": [
                {"itemId": line.sku, "quantity": line.quantity} for line in request.lines
            ],
        }
        payload = self._post("/orders", body)
        return GroceryOrderPlacement(
            provider_id=self._provider_id,
            external_order_id=str(payload.get("purchaseOrderId", "")),
            status=self._to_status(payload.get("orderStatus"), default=GroceryOrderStatus.PENDING),
            total=self._to_money(payload.get("orderTotal")),
        )

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        payload = self._get(f"/orders/{external_order_id}")
        return self._to_status(payload.get("orderStatus"), default=GroceryOrderStatus.UNKNOWN)

    # -- HTTP plumbing -----------------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers={"WM_SEC.ACCESS_TOKEN": self._api_key},
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
        """Translate one Walmart catalogue item into a domain :class:`GroceryProduct`."""
        unit = raw.get("unitOfMeasure")
        term = raw.get("searchTerm")
        return GroceryProduct(
            provider_id=self._provider_id,
            sku=str(raw.get("itemId", "")),
            name=str(raw.get("name", "")),
            price=_money_from_amount(raw.get("salePrice"), raw.get("currencyCode")),
            unit=unit if isinstance(unit, str) else None,
            in_stock=raw.get("stockStatus") == "AVAILABLE",
            matched_ingredient=term if isinstance(term, str) else None,
        )

    @staticmethod
    def _to_status(raw: object, *, default: GroceryOrderStatus) -> GroceryOrderStatus:
        """Map a Walmart order status (TitleCase, case-insensitive) onto the canonical lifecycle."""
        return _STATUS_MAP.get(str(raw or "").lower(), default)

    @staticmethod
    def _to_money(total: object) -> Money | None:
        """Translate an optional Walmart ``{amount, currencyCode}`` object into ``Money``."""
        if not isinstance(total, dict):
            return None
        return _money_from_amount(total.get("amount"), total.get("currencyCode"))
