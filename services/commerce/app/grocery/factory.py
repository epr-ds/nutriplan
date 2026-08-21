"""Choose the adapter backing each grocery provider (COM-403).

Central place that maps a provider id onto a concrete
:class:`~app.grocery.adapter.GroceryProviderAdapter`, mirroring the payment-provider factory. Until
the real sandbox integrations land (FreshBasket in COM-404, then Walmart/Chedraui in COM-405/406),
every provider is backed by the in-process :class:`~app.grocery.fake.FakeGroceryProviderAdapter`, so
search fans out end to end in dev/CI without a live provider. Later stories branch here on
``provider_id`` to return the real HTTP adapter, invisibly to everything above the ACL.
"""

from __future__ import annotations

from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.fake import FakeGroceryProviderAdapter


def build_grocery_adapter(provider_id: str) -> GroceryProviderAdapter:
    """Return the adapter for ``provider_id`` (currently the in-process fake for every provider)."""
    return FakeGroceryProviderAdapter(provider_id)
