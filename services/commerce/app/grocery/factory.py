"""Choose the adapter backing each grocery provider (COM-403, COM-404).

Central place that maps a provider id onto a concrete
:class:`~app.grocery.adapter.GroceryProviderAdapter`, mirroring the payment-provider factory. The
choice is invisible above the ACL.

FreshBasket (COM-404) is backed by the real
:class:`~app.grocery.freshbasket.FreshBasketGroceryAdapter` when a sandbox API key is configured
(``COMMERCE_FRESHBASKET_API_KEY``, injected from the vault in production per COM-905); with no key
-- as in dev/CI -- it falls back to the in-process
:class:`~app.grocery.fake.FakeGroceryProviderAdapter`, so grocery search fans out end to end without
credentials. Every other provider is the fake until its own adapter lands (Walmart COM-405, Chedraui
COM-406), at which point this factory branches on ``provider_id`` to return it.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.freshbasket import FreshBasketGroceryAdapter

_FRESHBASKET = "freshbasket"


def build_grocery_adapter(
    provider_id: str, *, settings: Settings | None = None
) -> GroceryProviderAdapter:
    """Return the adapter for ``provider_id`` (real FreshBasket when keyed, otherwise the fake)."""
    settings = settings or default_settings
    if provider_id == _FRESHBASKET:
        api_key = settings.freshbasket_api_key.get_secret_value()
        if api_key:
            return FreshBasketGroceryAdapter(
                api_key=api_key,
                base_url=settings.freshbasket_base_url,
                provider_id=provider_id,
                timeout=settings.http_timeout_seconds,
            )
    return FakeGroceryProviderAdapter(provider_id)
