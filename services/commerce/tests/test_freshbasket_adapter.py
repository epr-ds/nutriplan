"""COM-404: FreshBasket grocery adapter contract tests (no live FreshBasket).

An ``httpx.MockTransport`` stands in for the sandbox so the adapter's request shapes (path, method,
bearer auth, body) and response mapping (provider JSON -> domain vocabulary, provider status ->
canonical lifecycle, non-2xx / transport error -> ``GroceryProviderUnavailableError``) are exercised
deterministically. Asserts nothing provider-shaped -- no dict, wire field, or status string -- leaks
past the anti-corruption layer.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery_catalog import (
    GroceryOrderLine,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GroceryProduct,
    GrocerySearchItem,
    GrocerySearchQuery,
)
from app.domain.money import Money
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter

BASE_URL = "https://sandbox.freshbasket.mx/api/v1"
API_KEY = "sk-sandbox-freshbasket-abc123"  # gitleaks:allow


def _adapter(handler) -> FreshBasketGroceryAdapter:
    return FreshBasketGroceryAdapter(
        api_key=API_KEY, base_url=BASE_URL, transport=httpx.MockTransport(handler)
    )


def _ok(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


def _query(*ingredients: str, zip_code: str = "06700") -> GrocerySearchQuery:
    return GrocerySearchQuery(
        zip_code=zip_code,
        items=tuple(GrocerySearchItem(ingredient=name) for name in ingredients),
    )


# ---------------------------------------------------------------------------------- port + search


def test_adapter_satisfies_the_provider_port():
    adapter = _adapter(_ok({}))
    assert isinstance(adapter, GroceryProviderAdapter)
    assert adapter.provider_id == "freshbasket"


def test_search_sends_expected_request_and_maps_results():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("Authorization", "")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "sku": "fb-milk-1l",
                        "name": "Whole Milk 1L",
                        "priceCents": 2450,
                        "currency": "MXN",
                        "unit": "1 L",
                        "availability": "available",
                        "ingredient": "milk",
                    }
                ]
            },
        )

    result = _adapter(handler).search(_query("milk"))

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/catalog/search"
    assert captured["auth"] == f"Bearer {API_KEY}"
    assert captured["body"] == {"postalCode": "06700", "items": ["milk"]}

    assert result.provider_id == "freshbasket"
    assert len(result.products) == 1
    product = result.products[0]
    assert isinstance(product, GroceryProduct)
    assert product.sku == "fb-milk-1l"
    assert product.name == "Whole Milk 1L"
    assert product.price == Money(Decimal("24.50"), "MXN")
    assert product.unit == "1 L"
    assert product.in_stock is True
    assert product.matched_ingredient == "milk"


def test_search_marks_out_of_stock_items():
    handler = _ok(
        {
            "results": [
                {
                    "sku": "fb-bread-wg",
                    "name": "Whole-Grain Bread",
                    "priceCents": 3200,
                    "currency": "MXN",
                    "availability": "out_of_stock",
                    "ingredient": "bread",
                }
            ]
        }
    )
    product = _adapter(handler).search(_query("bread")).products[0]
    assert product.in_stock is False


def test_search_tolerates_a_missing_results_key():
    assert _adapter(_ok({})).search(_query("milk")).products == ()


@pytest.mark.parametrize("status_code", [400, 401, 429, 500, 503])
def test_search_raises_unavailable_on_error_status(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "nope"})

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).search(_query("milk"))


def test_search_raises_unavailable_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).search(_query("milk"))


# -------------------------------------------------------------------------------------- place_order


def _order() -> GroceryOrderRequest:
    return GroceryOrderRequest(
        provider_id="freshbasket",
        reference="np-order-77",
        zip_code="06700",
        lines=(GroceryOrderLine(sku="fb-milk-1l", quantity=2),),
    )


def test_place_order_sends_expected_request_and_maps_placement():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "orderId": "fb-ord-9",
                "status": "confirmed",
                "total": {"amountCents": 4900, "currency": "MXN"},
            },
        )

    placement = _adapter(handler).place_order(_order())

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/orders"
    assert captured["body"] == {
        "reference": "np-order-77",
        "postalCode": "06700",
        "lines": [{"sku": "fb-milk-1l", "quantity": 2}],
    }

    assert placement.provider_id == "freshbasket"
    assert placement.external_order_id == "fb-ord-9"
    assert placement.status is GroceryOrderStatus.CONFIRMED
    assert placement.total == Money(Decimal("49.00"), "MXN")


def test_place_order_defaults_unrecognised_status_to_pending_and_no_total():
    placement = _adapter(_ok({"orderId": "fb-ord-1", "status": "queued"})).place_order(_order())
    assert placement.status is GroceryOrderStatus.PENDING
    assert placement.total is None


def test_place_order_raises_unavailable_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={})

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).place_order(_order())


# ----------------------------------------------------------------------------------- order status


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [
        ("created", GroceryOrderStatus.PENDING),
        ("confirmed", GroceryOrderStatus.CONFIRMED),
        ("picking", GroceryOrderStatus.PREPARING),
        ("en_route", GroceryOrderStatus.OUT_FOR_DELIVERY),
        ("delivered", GroceryOrderStatus.DELIVERED),
        ("cancelled", GroceryOrderStatus.CANCELLED),
        ("failed", GroceryOrderStatus.FAILED),
    ],
)
def test_get_order_status_maps_provider_status(provider_status: str, expected: GroceryOrderStatus):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={"orderId": "fb-ord-9", "status": provider_status})

    assert _adapter(handler).get_order_status("fb-ord-9") == expected
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/orders/fb-ord-9"


def test_get_order_status_maps_unrecognised_value_to_unknown():
    status = _adapter(_ok({"status": "teleporting"})).get_order_status("fb-ord-9")
    assert status is GroceryOrderStatus.UNKNOWN


def test_get_order_status_raises_unavailable_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).get_order_status("fb-ord-9")
