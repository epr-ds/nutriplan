"""COM-402: the grocery provider anti-corruption layer (port + DTOs + fake adapter).

Proves the seam that later E4 stories build on: the provider-agnostic value objects are immutable,
the canonical order-status lifecycle is fixed, and the in-process fake adapter *translates* its
provider-shaped catalogue and status strings into domain vocabulary -- so no provider wire type
leaks past :class:`~app.grocery.adapter.GroceryProviderAdapter`.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.domain.errors import DomainError, GroceryProviderUnavailableError
from app.domain.grocery_catalog import (
    GroceryOrderLine,
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GroceryProduct,
    GrocerySearchItem,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.domain.money import Money
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.fake import FakeGroceryProviderAdapter


def _query(*ingredients: str, zip_code: str = "06700") -> GrocerySearchQuery:
    return GrocerySearchQuery(
        zip_code=zip_code,
        items=tuple(GrocerySearchItem(ingredient=name) for name in ingredients),
    )


class TestVocabulary:
    def test_value_objects_are_immutable(self) -> None:
        product = GroceryProduct(provider_id="fake", sku="s", name="n", price=Money(Decimal("1")))
        with pytest.raises(dataclasses.FrozenInstanceError):
            product.name = "other"  # type: ignore[misc]

    def test_status_lifecycle_values(self) -> None:
        assert GroceryOrderStatus.OUT_FOR_DELIVERY == "out_for_delivery"
        assert GroceryOrderStatus("pending") is GroceryOrderStatus.PENDING
        assert GroceryOrderStatus.UNKNOWN.value == "unknown"

    def test_query_and_order_defaults(self) -> None:
        assert _query("milk").items[0].quantity is None
        request = GroceryOrderRequest(provider_id="fake", reference="o1", zip_code="06700")
        assert request.lines == ()
        placement = GroceryOrderPlacement(provider_id="fake", external_order_id="x")
        assert placement.status is GroceryOrderStatus.PENDING
        assert placement.total is None

    def test_provider_unavailable_is_a_domain_error(self) -> None:
        err = GroceryProviderUnavailableError("freshbasket")
        assert isinstance(err, DomainError)
        assert err.provider_id == "freshbasket"


class TestFakeAdapter:
    def test_satisfies_the_port(self) -> None:
        assert isinstance(FakeGroceryProviderAdapter(), GroceryProviderAdapter)

    def test_search_maps_provider_payload_to_domain_products(self) -> None:
        adapter = FakeGroceryProviderAdapter("freshbasket")
        result = adapter.search(_query("milk", "eggs"))
        assert isinstance(result, GrocerySearchResult)
        assert result.provider_id == "freshbasket"
        # Every hit is a domain GroceryProduct with normalised Money -- no provider dict leaks.
        assert result.products and all(isinstance(p, GroceryProduct) for p in result.products)
        assert all(isinstance(p.price, Money) for p in result.products)
        milk = next(p for p in result.products if p.matched_ingredient == "milk")
        assert milk.sku == "fb-milk-1l"
        assert milk.name == "Whole Milk 1L"
        assert milk.price == Money(Decimal("24.50"))
        assert milk.provider_id == "freshbasket"
        assert milk.in_stock is True

    def test_search_marks_out_of_stock_and_skips_unknown_ingredients(self) -> None:
        adapter = FakeGroceryProviderAdapter()
        result = adapter.search(_query("bread", "unobtanium"))
        assert [p.sku for p in result.products] == ["fb-bread-wg"]
        assert result.products[0].in_stock is False

    def test_place_order_records_request_and_returns_pending(self) -> None:
        adapter = FakeGroceryProviderAdapter("freshbasket")
        request = GroceryOrderRequest(
            provider_id="freshbasket",
            reference="order-123",
            zip_code="06700",
            lines=(GroceryOrderLine(sku="fb-milk-1l", quantity=2),),
        )
        placement = adapter.place_order(request)
        assert isinstance(placement, GroceryOrderPlacement)
        assert placement.provider_id == "freshbasket"
        assert placement.external_order_id.startswith("freshbasket_ord_")
        assert placement.status is GroceryOrderStatus.PENDING
        assert adapter.orders == [request]

    def test_get_order_status_maps_provider_strings_to_canonical(self) -> None:
        adapter = FakeGroceryProviderAdapter()
        assert adapter.get_order_status("fake_ord_abc") is GroceryOrderStatus.PENDING
        dispatched = adapter.get_order_status("fake_ord_abc:dispatched")
        assert dispatched is GroceryOrderStatus.OUT_FOR_DELIVERY
        assert adapter.get_order_status("fake_ord_abc:delivered") is GroceryOrderStatus.DELIVERED
        assert adapter.get_order_status("fake_ord_abc:rejected") is GroceryOrderStatus.FAILED

    def test_unknown_provider_status_maps_to_unknown_not_raw(self) -> None:
        adapter = FakeGroceryProviderAdapter()
        assert adapter.get_order_status("fake_ord_abc:teleporting") is GroceryOrderStatus.UNKNOWN
