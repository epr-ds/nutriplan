"""COM-401: grocery provider registry — domain policy, use case, and HTTP endpoint.

Covers the pure enable/disable policy (:class:`GroceryProviderRegistry`), the thin application
service, and ``GET /fulfillment/grocery/providers`` end to end via dependency overrides (auth stub +
a fixed registry), plus one test that exercises the real config wiring (the default catalogue only
surfaces the providers enabled for this environment). No database is involved — the registry is a
read-only, config-driven computation.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_list_grocery_providers_service, get_token_verifier
from app.application.list_grocery_providers import ListGroceryProvidersService
from app.core.principal import Principal
from app.domain.enums import ProviderType
from app.domain.grocery import GroceryProvider, GroceryProviderRegistry
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
WALMART = GroceryProvider(id="walmart", name="Walmart Súper", enabled=False)
CHEDRAUI = GroceryProvider(id="chedraui", name="Chedraui", enabled=True)
REGISTRY = GroceryProviderRegistry(providers=(FRESH, WALMART, CHEDRAUI))

# ------------------------------------------------------------------------ domain: enable/disable


def test_available_returns_only_enabled_providers():
    assert REGISTRY.available() == (FRESH, CHEDRAUI)


def test_available_preserves_configured_order():
    ordered = GroceryProviderRegistry(providers=(CHEDRAUI, FRESH))
    assert [p.id for p in ordered.available()] == ["chedraui", "freshbasket"]


def test_available_is_empty_when_all_disabled():
    registry = GroceryProviderRegistry(
        providers=(WALMART, GroceryProvider(id="x", name="X", enabled=False))
    )
    assert registry.available() == ()


def test_available_is_empty_for_an_empty_registry():
    assert GroceryProviderRegistry().available() == ()


def test_provider_defaults_to_enabled_grocery_type():
    provider = GroceryProvider(id="p", name="P")
    assert provider.enabled is True
    assert provider.type is ProviderType.GROCERY


# ----------------------------------------------------------------------------- application service


def test_service_lists_the_enabled_providers():
    service = ListGroceryProvidersService(REGISTRY)
    assert service.list_available() == (FRESH, CHEDRAUI)


def test_service_over_empty_registry_lists_nothing():
    service = ListGroceryProvidersService(GroceryProviderRegistry())
    assert service.list_available() == ()


# --------------------------------------------------------------------------------------- API layer

_URL = "/fulfillment/grocery/providers"


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_list_grocery_providers_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*, stub_registry: GroceryProviderRegistry | None = None) -> TestClient:
    if stub_registry is not None:
        app.dependency_overrides[get_list_grocery_providers_service] = lambda: (
            ListGroceryProvidersService(stub_registry)
        )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_returns_enabled_providers_as_camel_case():
    client = _build(stub_registry=REGISTRY)

    response = client.get(_URL, headers=_auth())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == [
        {
            "id": "freshbasket",
            "name": "FreshBasket",
            "type": "grocery",
            "logoUrl": "https://cdn.example.mx/freshbasket.png",
            "estimatedDelivery": "Same day, 1-2 h",
        },
        {
            "id": "chedraui",
            "name": "Chedraui",
            "type": "grocery",
            "logoUrl": None,
            "estimatedDelivery": None,
        },
    ]


def test_api_returns_empty_list_when_no_provider_is_enabled():
    client = _build(stub_registry=GroceryProviderRegistry(providers=(WALMART,)))

    response = client.get(_URL, headers=_auth())

    assert response.status_code == 200
    assert response.json() == []


def test_api_requires_authentication():
    client = _build(stub_registry=REGISTRY)

    assert client.get(_URL).status_code == 401


def test_api_rejects_unknown_token():
    client = _build(stub_registry=REGISTRY)

    assert client.get(_URL, headers=_auth("nope")).status_code == 401


def test_api_real_wiring_lists_only_enabled_default_providers():
    # No service override: exercises config -> deps -> domain for real. The default catalogue
    # enables all three sandbox providers (FreshBasket, Walmart, Chedraui) for M5, in catalogue
    # order.
    client = _build()

    response = client.get(_URL, headers=_auth())

    assert response.status_code == 200
    providers = response.json()
    ids = [p["id"] for p in providers]
    assert ids == ["freshbasket", "walmart", "chedraui"]
    assert providers[0]["name"] == "FreshBasket"
    assert providers[0]["type"] == "grocery"
    assert providers[1]["name"] == "Walmart Súper"
    assert providers[2]["name"] == "Chedraui"
