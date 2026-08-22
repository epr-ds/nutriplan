"""COM-405: Walmart grocery adapter contract tests (no live Walmart).

An ``httpx.MockTransport`` stands in for the sandbox so the adapter's request shapes (path, method,
``WM_SEC.ACCESS_TOKEN`` auth header, body) and response mapping (Walmart JSON -> domain vocabulary,
decimal ``salePrice`` -> ``Money``, TitleCase status -> canonical lifecycle, non-2xx / transport
error -> ``GroceryProviderUnavailableError``) are exercised deterministically. Asserts nothing
Walmart-shaped -- no dict, wire field, or status string -- leaks past the anti-corruption layer.

Walmart deliberately speaks a different dialect than FreshBasket (COM-404): a non-bearer auth
header, decimal-currency prices (not integer cents), and TitleCase statuses -- proving the single
ACL absorbs provider differences.
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
from app.grocery.walmart import WalmartGroceryAdapter

BASE_URL = "https://sandbox.walmart.com.mx/api/v3"
API_KEY = "wm-sandbox-walmart-abc123"  # gitleaks:allow


def _adapter(handler) -> WalmartGroceryAdapter:
    return WalmartGroceryAdapter(
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
    assert adapter.provider_id == "walmart"


def test_search_sends_expected_request_and_maps_results():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("WM_SEC.ACCESS_TOKEN", "")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "itemId": "wm-milk-1l",
                        "name": "Whole Milk 1L",
                        "salePrice": 24.50,
                        "currencyCode": "MXN",
                        "unitOfMeasure": "1 L",
                        "stockStatus": "AVAILABLE",
                        "searchTerm": "milk",
                    }
                ]
            },
        )

    result = _adapter(handler).search(_query("milk"))

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v3/items/search"
    assert captured["auth"] == API_KEY
    assert captured["body"] == {"searchTerms": ["milk"], "shipToPostalCode": "06700"}

    assert result.provider_id == "walmart"
    assert len(result.products) == 1
    product = result.products[0]
    assert isinstance(product, GroceryProduct)
    assert product.sku == "wm-milk-1l"
    assert product.name == "Whole Milk 1L"
    assert product.price == Money(Decimal("24.50"), "MXN")
    assert product.unit == "1 L"
    assert product.in_stock is True
    assert product.matched_ingredient == "milk"


def test_search_marks_out_of_stock_items():
    handler = _ok(
        {
            "items": [
                {
                    "itemId": "wm-bread-wg",
                    "name": "Whole-Grain Bread",
                    "salePrice": 32.00,
                    "currencyCode": "MXN",
                    "stockStatus": "OUT_OF_STOCK",
                    "searchTerm": "bread",
                }
            ]
        }
    )
    product = _adapter(handler).search(_query("bread")).products[0]
    assert product.in_stock is False


def test_search_tolerates_a_missing_items_key():
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
        provider_id="walmart",
        reference="np-order-77",
        zip_code="06700",
        lines=(GroceryOrderLine(sku="wm-milk-1l", quantity=2),),
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
                "purchaseOrderId": "wm-ord-9",
                "orderStatus": "Acknowledged",
                "orderTotal": {"amount": 49.00, "currencyCode": "MXN"},
            },
        )

    placement = _adapter(handler).place_order(_order())

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v3/orders"
    assert captured["body"] == {
        "purchaseOrderId": "np-order-77",
        "shipToPostalCode": "06700",
        "orderLines": [{"itemId": "wm-milk-1l", "quantity": 2}],
    }

    assert placement.provider_id == "walmart"
    assert placement.external_order_id == "wm-ord-9"
    assert placement.status is GroceryOrderStatus.CONFIRMED
    assert placement.total == Money(Decimal("49.00"), "MXN")


def test_place_order_defaults_unrecognised_status_to_pending_and_no_total():
    placement = _adapter(_ok({"purchaseOrderId": "wm-ord-1", "orderStatus": "Queued"})).place_order(
        _order()
    )
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
        ("Created", GroceryOrderStatus.PENDING),
        ("Acknowledged", GroceryOrderStatus.CONFIRMED),
        ("Preparing", GroceryOrderStatus.PREPARING),
        ("Shipped", GroceryOrderStatus.OUT_FOR_DELIVERY),
        ("Delivered", GroceryOrderStatus.DELIVERED),
        ("Cancelled", GroceryOrderStatus.CANCELLED),
        ("Failed", GroceryOrderStatus.FAILED),
    ],
)
def test_get_order_status_maps_provider_status(provider_status: str, expected: GroceryOrderStatus):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(
            200, json={"purchaseOrderId": "wm-ord-9", "orderStatus": provider_status}
        )

    assert _adapter(handler).get_order_status("wm-ord-9") == expected
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v3/orders/wm-ord-9"


def test_get_order_status_maps_unrecognised_value_to_unknown():
    status = _adapter(_ok({"orderStatus": "Teleporting"})).get_order_status("wm-ord-9")
    assert status is GroceryOrderStatus.UNKNOWN


def test_get_order_status_raises_unavailable_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).get_order_status("wm-ord-9")
