"""COM-404: the grocery adapter factory selects FreshBasket vs the fake by configuration.

Guards the COM-905 credential seam: FreshBasket is backed by the real HTTP adapter only when a
sandbox API key is configured, and by the in-process fake otherwise (dev/CI), while every other
provider stays on the fake for now.
"""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import Settings
from app.grocery.factory import build_grocery_adapter
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter


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


def test_uses_the_fake_for_other_providers_even_with_a_freshbasket_key():
    settings = _settings(freshbasket_api_key=SecretStr("sk-sandbox-abc"))  # gitleaks:allow
    adapter = build_grocery_adapter("walmart", settings=settings)
    assert isinstance(adapter, FakeGroceryProviderAdapter)
    assert adapter.provider_id == "walmart"
