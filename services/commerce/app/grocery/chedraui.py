"""Chedraui grocery provider adapter (COM-406) -- the third real ``GroceryProviderAdapter``.

The fast-follow that completes NutriPlan's M5 grocery provider set (after FreshBasket COM-404 and
Walmart COM-405), all behind the single COM-402 anti-corruption layer. Chedraui speaks its own
sandbox REST dialect -- and, being a Mexican retailer, a *Spanish-language* one: an ``X-Api-Key``
auth header, Spanish request/response field names (``codigoPostal``, ``articulos``, ``productos``,
``precio``, ``estado``...), **string-encoded decimal prices** (``"24.50"``, not integer cents nor a
JSON number), a **boolean** ``disponible`` availability flag (not a status enum), and Spanish
fulfilment statuses (``creado``, ``entregado``...). None of it leaks: everything is translated to
and from the provider-agnostic vocabulary in :mod:`app.domain.grocery_catalog`, proving the one ACL
absorbs a third, structurally distinct provider without any change above the seam.

A synchronous ``httpx.Client`` keeps the request path consistent with the service's sync stack, and
a ``transport`` can be injected so the mapping is unit-testable without a live Chedraui. Every
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

_PROVIDER_ID = "chedraui"

# Chedraui's Spanish fulfilment vocabulary -> our canonical lifecycle. Matched case-insensitively;
# an unrecognised value maps to UNKNOWN (for a status poll) or PENDING (for a fresh placement) so
# the raw provider string never leaks past the ACL.
_STATUS_MAP: dict[str, GroceryOrderStatus] = {
    "creado": GroceryOrderStatus.PENDING,
    "confirmado": GroceryOrderStatus.CONFIRMED,
    "preparando": GroceryOrderStatus.PREPARING,
    "enviado": GroceryOrderStatus.OUT_FOR_DELIVERY,
    "entregado": GroceryOrderStatus.DELIVERED,
    "cancelado": GroceryOrderStatus.CANCELLED,
    "fallido": GroceryOrderStatus.FAILED,
}


def _money_from_text(amount: object, currency: object) -> Money:
    """Translate Chedraui's string-encoded decimal amount + code into domain :class:`Money`."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        value = Decimal(0)
    return Money(value, str(currency) if currency else "MXN")


class ChedrauiGroceryAdapter:
    """Searches, orders, and reports status against Chedraui's sandbox REST API (COM-406)."""

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
            "codigoPostal": query.zip_code,
            "articulos": [item.ingredient for item in query.items],
        }
        payload = self._post("/busqueda", body)
        products = tuple(
            self._to_product(raw) for raw in payload.get("productos") or [] if isinstance(raw, dict)
        )
        return GrocerySearchResult(provider_id=self._provider_id, products=products)

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        body = {
            "referencia": request.reference,
            "codigoPostal": request.zip_code,
            "articulos": [{"clave": line.sku, "cantidad": line.quantity} for line in request.lines],
        }
        payload = self._post("/pedidos", body)
        return GroceryOrderPlacement(
            provider_id=self._provider_id,
            external_order_id=str(payload.get("pedidoId", "")),
            status=self._to_status(payload.get("estado"), default=GroceryOrderStatus.PENDING),
            total=self._to_money(payload.get("importe")),
        )

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        payload = self._get(f"/pedidos/{external_order_id}")
        return self._to_status(payload.get("estado"), default=GroceryOrderStatus.UNKNOWN)

    # -- HTTP plumbing -----------------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers={"X-Api-Key": self._api_key},
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
        """Translate one Chedraui catalogue item into a domain :class:`GroceryProduct`."""
        unit = raw.get("unidad")
        term = raw.get("ingrediente")
        return GroceryProduct(
            provider_id=self._provider_id,
            sku=str(raw.get("clave", "")),
            name=str(raw.get("nombre", "")),
            price=_money_from_text(raw.get("precio"), raw.get("moneda")),
            unit=unit if isinstance(unit, str) else None,
            in_stock=bool(raw.get("disponible")),
            matched_ingredient=term if isinstance(term, str) else None,
        )

    @staticmethod
    def _to_status(raw: object, *, default: GroceryOrderStatus) -> GroceryOrderStatus:
        """Map a Chedraui order status (Spanish, case-insensitive) onto the canonical lifecycle."""
        return _STATUS_MAP.get(str(raw or "").lower(), default)

    @staticmethod
    def _to_money(importe: object) -> Money | None:
        """Translate an optional Chedraui ``{total, moneda}`` object into ``Money``."""
        if not isinstance(importe, dict):
            return None
        return _money_from_text(importe.get("total"), importe.get("moneda"))
