"""COM-404/405/406: the grocery adapter factory selects a real adapter vs the fake by configuration.

Guards the COM-905 credential seam: FreshBasket (COM-404), Walmart (COM-405), and Chedraui (COM-406)
are each backed by their real HTTP adapter only when a sandbox API key is configured, and by the
in-process fake otherwise (dev/CI), while every other provider stays on the fake for now.
"""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import Settings
from app.grocery.chedraui import ChedrauiGroceryAdapter
from app.grocery.factory import build_grocery_adapter
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter
from app.grocery.walmart import WalmartGroceryAdapter


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_builds_real_freshbasket_adapter_when_a_sandbox_key_is_configured():
    settings = _settings(freshbasket_api_key=SecretStr("sk-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("freshbasket", settings=settings)
    assert isinstance(adapter, FreshBasketGroceryAdapter)
    assert adapter.provider_id == "freshbasket"


def test_falls_back_to_the_fake_for_freshbasket_without_a_key():
    settings = _settings(freshbasket_api_key=SecretStr(""))
    adapter = build_grocery_adapter("freshbasket", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "freshbasket"


def test_builds_real_walmart_adapter_when_a_sandbox_key_is_configured():
    settings = _settings(walmart_api_key=SecretStr("wm-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("walmart", settings=settings)
    assert isinstance(adapter, WalmartGroceryAdapter)
    assert adapter.provider_id == "walmart"


def test_falls_back_to_the_fake_for_walmart_without_a_key():
    settings = _settings(walmart_api_key=SecretStr(""))
    adapter = build_grocery_adapter("walmart", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "walmart"


def test_uses_the_fake_for_other_providers_even_with_a_freshbasket_key():
    settings = _settings(freshbasket_api_key=SecretStr("sk-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("walmart", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "walmart"


def test_uses_the_fake_for_chedraui_even_with_a_walmart_key():
    settings = _settings(walmart_api_key=SecretStr("wm-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("chedraui", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "chedraui"


def test_builds_real_chedraui_adapter_when_a_sandbox_key_is_configured():
    settings = _settings(chedraui_api_key=SecretStr("ch-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("chedraui", settings=settings)
    assert isinstance(adapter, ChedrauiGroceryAdapter)
    assert adapter.provider_id == "chedraui"


def test_falls_back_to_the_fake_for_chedraui_without_a_key():
    settings = _settings(chedraui_api_key=SecretStr(""))
    adapter = build_grocery_adapter("chedraui", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "chedraui"
