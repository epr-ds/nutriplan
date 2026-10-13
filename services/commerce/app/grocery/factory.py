"""Choose the adapter backing each grocery provider (COM-403, COM-404, COM-405, COM-406).

Central place that maps a provider id onto a concrete
:class:`~app.grocery.adapter.GroceryProviderAdapter`, mirroring the payment-provider factory. The
choice is invisible above the ACL.

FreshBasket (COM-404), Walmart (COM-405), and Chedraui (COM-406) are each backed by their real HTTP
adapter when a sandbox API key is configured (``COMMERCE_FRESHBASKET_API_KEY`` /
``COMMERCE_WALMART_API_KEY`` / ``COMMERCE_CHEDRAUI_API_KEY``, injected from the vault in production
per COM-905); with no key -- as in dev/CI -- the provider falls back to the in-process
:class:`~app.grocery.fake.FakeGroceryProviderAdapter`, so grocery search fans out end to end without
credentials. Any provider without its own adapter stays on the fake until one lands, at which point
this factory grows one more branch.

Each real adapter is built with that provider's own request timeout (COM-407):
``GroceryProviderSetting.timeout_seconds`` when the catalogue sets one, otherwise the service-wide
``http_timeout_seconds``. Wrapping the adapter in its circuit breaker is the composition root's job
(``app.api.deps``), so this factory stays focused on *which* implementation backs a provider.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.chedraui import ChedrauiGroceryAdapter
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter
from app.grocery.walmart import WalmartGroceryAdapter

_FRESHBASKET = "freshbasket"
_WALMART = "walmart"
_CHEDRAUI = "chedraui"


def _timeout_for(provider_id: str, settings: Settings) -> float:
    """Return the provider's own request timeout, falling back to the service-wide one (COM-407)."""
    for provider in settings.grocery_providers:
        if provider.id == provider_id and provider.timeout_seconds is not None:
            return provider.timeout_seconds
    return settings.http_timeout_seconds


def build_grocery_adapter(
    provider_id: str, *, settings: Settings | None = None
) -> GroceryProviderAdapter:
    """Return the adapter for ``provider_id`` (a real HTTP adapter when keyed, else the fake)."""
    settings = settings or default_settings
    timeout = _timeout_for(provider_id, settings)
    if provider_id == _FRESHBASKET:
        api_key = settings.freshbasket_api_key.get_secret_value()
        if api_key:
            return FreshBasketGroceryAdapter(
                api_key=api_key,
                base_url=settings.freshbasket_base_url,
                provider_id=provider_id,
                timeout=timeout,
            )
    elif provider_id == _WALMART:
        api_key = settings.walmart_api_key.get_secret_value()
        if api_key:
            return WalmartGroceryAdapter(
                api_key=api_key,
                base_url=settings.walmart_base_url,
                provider_id=provider_id,
                timeout=timeout,
            )
    elif provider_id == _CHEDRAUI:
        api_key = settings.chedraui_api_key.get_secret_value()
        if api_key:
            return ChedrauiGroceryAdapter(
                api_key=api_key,
                base_url=settings.chedraui_base_url,
                provider_id=provider_id,
                timeout=timeout,
            )
    return FakeGroceryProviderAdapter(provider_id)
