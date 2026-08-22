"""COM-406: Chedraui grocery adapter contract tests (no live Chedraui).

An ``httpx.MockTransport`` stands in for the sandbox so the adapter's request shapes (path, method,
``X-Api-Key`` auth header, Spanish body fields) and response mapping (Chedraui JSON -> domain
vocabulary, string-decimal ``precio`` -> ``Money``, boolean ``disponible`` -> ``in_stock``, Spanish
``estado`` -> canonical lifecycle, non-2xx / transport error -> ``GroceryProviderUnavailableError``)
are exercised deterministically. Asserts nothing Chedraui-shaped -- no dict, wire field, or status
string -- leaks past the anti-corruption layer.

Chedraui is a third distinct dialect after FreshBasket (COM-404) and Walmart (COM-405): an
``X-Api-Key`` header, Spanish field names, a boolean availability flag, and string-encoded decimal
prices -- proving the single ACL absorbs a structurally different provider.
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
from app.grocery.chedraui import ChedrauiGroceryAdapter

BASE_URL = "https://sandbox.chedraui.com.mx/api/v2"
API_KEY = "ch-sandbox-chedraui-abc123"  # gitleaks:allow


def _adapter(handler) -> ChedrauiGroceryAdapter:
    return ChedrauiGroceryAdapter(
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
    assert adapter.provider_id == "chedraui"


def test_search_sends_expected_request_and_maps_results():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("X-Api-Key", "")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "productos": [
                    {
                        "clave": "ch-milk-1l",
                        "nombre": "Whole Milk 1L",
                        "precio": "24.50",
                        "moneda": "MXN",
                        "unidad": "1 L",
                        "disponible": True,
                        "ingrediente": "milk",
                    }
                ]
            },
        )

    result = _adapter(handler).search(_query("milk"))

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/busqueda"
    assert captured["auth"] == API_KEY
    assert captured["body"] == {"codigoPostal": "06700", "articulos": ["milk"]}

    assert result.provider_id == "chedraui"
    assert len(result.products) == 1
    product = result.products[0]
    assert isinstance(product, GroceryProduct)
    assert product.sku == "ch-milk-1l"
    assert product.name == "Whole Milk 1L"
    assert product.price == Money(Decimal("24.50"), "MXN")
    assert product.unit == "1 L"
    assert product.in_stock is True
    assert product.matched_ingredient == "milk"


def test_search_marks_out_of_stock_items():
    handler = _ok(
        {
            "productos": [
                {
                    "clave": "ch-bread-wg",
                    "nombre": "Whole-Grain Bread",
                    "precio": "32.00",
                    "moneda": "MXN",
                    "disponible": False,
                    "ingrediente": "bread",
                }
            ]
        }
    )
    product = _adapter(handler).search(_query("bread")).products[0]
    assert product.in_stock is False


def test_search_tolerates_a_missing_productos_key():
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
        provider_id="chedraui",
        reference="np-order-77",
        zip_code="06700",
        lines=(GroceryOrderLine(sku="ch-milk-1l", quantity=2),),
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
                "pedidoId": "ch-ord-9",
                "estado": "confirmado",
                "importe": {"total": "49.00", "moneda": "MXN"},
            },
        )

    placement = _adapter(handler).place_order(_order())

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/pedidos"
    assert captured["body"] == {
        "referencia": "np-order-77",
        "codigoPostal": "06700",
        "articulos": [{"clave": "ch-milk-1l", "cantidad": 2}],
    }

    assert placement.provider_id == "chedraui"
    assert placement.external_order_id == "ch-ord-9"
    assert placement.status is GroceryOrderStatus.CONFIRMED
    assert placement.total == Money(Decimal("49.00"), "MXN")


def test_place_order_defaults_unrecognised_status_to_pending_and_no_total():
    placement = _adapter(_ok({"pedidoId": "ch-ord-1", "estado": "encolado"})).place_order(_order())
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
        ("creado", GroceryOrderStatus.PENDING),
        ("confirmado", GroceryOrderStatus.CONFIRMED),
        ("preparando", GroceryOrderStatus.PREPARING),
        ("enviado", GroceryOrderStatus.OUT_FOR_DELIVERY),
        ("entregado", GroceryOrderStatus.DELIVERED),
        ("cancelado", GroceryOrderStatus.CANCELLED),
        ("fallido", GroceryOrderStatus.FAILED),
    ],
)
def test_get_order_status_maps_provider_status(provider_status: str, expected: GroceryOrderStatus):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={"pedidoId": "ch-ord-9", "estado": provider_status})

    assert _adapter(handler).get_order_status("ch-ord-9") == expected
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v2/pedidos/ch-ord-9"


def test_get_order_status_maps_unrecognised_value_to_unknown():
    status = _adapter(_ok({"estado": "teletransportando"})).get_order_status("ch-ord-9")
    assert status is GroceryOrderStatus.UNKNOWN


def test_get_order_status_raises_unavailable_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(GroceryProviderUnavailableError):
        _adapter(handler).get_order_status("ch-ord-9")
