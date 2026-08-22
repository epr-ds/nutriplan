"""COM-403: grocery product search across providers -- fan-out service and HTTP endpoint.

Covers the cross-provider search use case (fan-out to enabled providers via the COM-402 ACL, the
optional ``providers`` filter, configured ordering, and resilience to an unavailable provider) and
``POST /fulfillment/grocery/search`` end to end via dependency overrides (auth stub + a fixed
service), plus one test that exercises the real config/adapter wiring. No database is involved.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_search_grocery_products_service, get_token_verifier
from app.application.search_grocery_products import SearchGroceryProductsService
from app.core.principal import Principal
from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery import GroceryProvider, GroceryProviderRegistry
from app.domain.grocery_catalog import (
    GroceryOrderStatus,
    GrocerySearchItem,
    GrocerySearchQuery,
)
from app.grocery.fake import FakeGroceryProviderAdapter
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

FRESH = GroceryProvider(
    id="freshbasket",
    name="FreshBasket",
    enabled=True,
    logo_url="https://cdn.example.mx/freshbasket.png",
    estimated_delivery="Same day, 1-2 h",
)
WALMART = GroceryProvider(id="walmart", name="Walmart Super", enabled=True)
CHEDRAUI = GroceryProvider(id="chedraui", name="Chedraui", enabled=False)


def _catalogue(ingredient: str, sku: str, title: str, cents: int) -> dict:
    entry = {"id": sku, "title": title, "price_cents": cents, "availability": "in_stock"}
    return {ingredient: [entry]}


_MILK = _catalogue("milk", "m1", "Milk 1L", 2000)
_EGGS = _catalogue("eggs", "e1", "Eggs 12", 3000)


class _BoomAdapter:
    """An adapter whose every call reports the provider is unavailable (COM-402/407 seam)."""

    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def search(self, query: GrocerySearchQuery):  # noqa: ANN201 - test stub
        raise GroceryProviderUnavailableError(self._provider_id)

    def place_order(self, request):  # noqa: ANN001, ANN201 - test stub
        raise GroceryProviderUnavailableError(self._provider_id)

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        raise GroceryProviderUnavailableError(self._provider_id)


def _fake(provider_id: str, catalogue: dict) -> FakeGroceryProviderAdapter:
    return FakeGroceryProviderAdapter(provider_id, catalogue=catalogue)


def _query(*ingredients: str, providers: tuple[str, ...] = ()) -> GrocerySearchQuery:
    return GrocerySearchQuery(
        zip_code="06700",
        items=tuple(GrocerySearchItem(ingredient=name) for name in ingredients),
        providers=providers,
    )


# ----------------------------------------------------------------------------- application service


def test_fan_out_returns_only_providers_with_matches():
    registry = GroceryProviderRegistry(providers=(FRESH, WALMART))
    service = SearchGroceryProductsService(
        registry, {"freshbasket": _fake("freshbasket", _MILK), "walmart": _fake("walmart", _EGGS)}
    )
    assert service.search(_query("milk")) == (FRESH,)
    assert service.search(_query("eggs")) == (WALMART,)
    assert service.search(_query("milk", "eggs")) == (FRESH, WALMART)


def test_fan_out_is_empty_when_nothing_matches():
    registry = GroceryProviderRegistry(providers=(FRESH,))
    service = SearchGroceryProductsService(registry, {"freshbasket": _fake("freshbasket", _MILK)})
    assert service.search(_query("unobtanium")) == ()


def test_fan_out_preserves_configured_provider_order():
    registry = GroceryProviderRegistry(providers=(WALMART, FRESH))
    service = SearchGroceryProductsService(
        registry, {"walmart": _fake("walmart", _MILK), "freshbasket": _fake("freshbasket", _MILK)}
    )
    assert service.search(_query("milk")) == (WALMART, FRESH)


def test_disabled_providers_are_never_queried():
    registry = GroceryProviderRegistry(providers=(FRESH, CHEDRAUI))
    service = SearchGroceryProductsService(
        registry,
        {"freshbasket": _fake("freshbasket", _MILK), "chedraui": _fake("chedraui", _MILK)},
    )
    assert service.search(_query("milk")) == (FRESH,)


def test_providers_filter_restricts_the_fan_out():
    registry = GroceryProviderRegistry(providers=(FRESH, WALMART))
    service = SearchGroceryProductsService(
        registry, {"freshbasket": _fake("freshbasket", _MILK), "walmart": _fake("walmart", _MILK)}
    )
    assert service.search(_query("milk", providers=("walmart",))) == (WALMART,)


def test_an_unavailable_provider_is_skipped_not_fatal():
    registry = GroceryProviderRegistry(providers=(FRESH, WALMART))
    service = SearchGroceryProductsService(
        registry, {"freshbasket": _BoomAdapter("freshbasket"), "walmart": _fake("walmart", _MILK)}
    )
    assert service.search(_query("milk")) == (WALMART,)


def test_provider_without_a_wired_adapter_is_skipped():
    registry = GroceryProviderRegistry(providers=(FRESH,))
    service = SearchGroceryProductsService(registry, {})
    assert service.search(_query("milk")) == ()


# --------------------------------------------------------------------------------------- API layer

_URL = "/fulfillment/grocery/search"


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_search_grocery_products_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*, service: SearchGroceryProductsService | None = None) -> TestClient:
    if service is not None:
        app.dependency_overrides[get_search_grocery_products_service] = lambda: service
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(*ingredients: str, zip_code: str = "06700") -> dict:
    return {"items": [{"ingredient": name} for name in ingredients], "zipCode": zip_code}


def test_api_returns_matching_providers_as_camel_case():
    service = SearchGroceryProductsService(
        GroceryProviderRegistry(providers=(FRESH,)),
        {"freshbasket": _fake("freshbasket", _MILK)},
    )
    client = _build(service=service)

    response = client.post(_URL, json=_body("milk"), headers=_auth())

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "freshbasket",
            "name": "FreshBasket",
            "type": "grocery",
            "logoUrl": "https://cdn.example.mx/freshbasket.png",
            "estimatedDelivery": "Same day, 1-2 h",
        }
    ]


def test_api_returns_empty_list_when_no_provider_matches():
    service = SearchGroceryProductsService(
        GroceryProviderRegistry(providers=(FRESH,)),
        {"freshbasket": _fake("freshbasket", _MILK)},
    )
    client = _build(service=service)

    response = client.post(_URL, json=_body("unobtanium"), headers=_auth())

    assert response.status_code == 200
    assert response.json() == []


def test_api_requires_authentication():
    client = _build(
        service=SearchGroceryProductsService(GroceryProviderRegistry(), {}),
    )
    assert client.post(_URL, json=_body("milk")).status_code == 401


def test_api_rejects_empty_items():
    client = _build(service=SearchGroceryProductsService(GroceryProviderRegistry(), {}))
    response = client.post(_URL, json={"items": [], "zipCode": "06700"}, headers=_auth())
    assert response.status_code == 422


def test_api_rejects_a_non_five_digit_zip_code():
    client = _build(service=SearchGroceryProductsService(GroceryProviderRegistry(), {}))
    response = client.post(_URL, json=_body("milk", zip_code="abc"), headers=_auth())
    assert response.status_code == 422


def test_api_real_wiring_searches_default_provider():
    # No service override: exercises config -> registry -> adapters -> service for real. The
    # default catalogue enables FreshBasket and Walmart; both run on the fake adapter in CI (no
    # sandbox key), whose catalogue carries milk, so both fulfil the search.
    client = _build()

    response = client.post(_URL, json=_body("milk"), headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert [p["id"] for p in body] == ["freshbasket", "walmart"]
