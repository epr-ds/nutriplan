"""Build a :class:`~app.cache.cache.ResponseCache` from configuration."""

from __future__ import annotations

from app.cache.cache import ResponseCache
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.kv.factory import build_key_value_store
from app.kv.store import KeyValueStore


def build_response_cache(
    settings: Settings | None = None,
    store: KeyValueStore | None = None,
) -> ResponseCache:
    """Construct the response cache, sharing a store with the budget guard when given."""
    settings = settings or default_settings
    store = store or build_key_value_store(settings)
    return ResponseCache(
        store,
        ttl_seconds=settings.cache_ttl_seconds,
        namespace=settings.cache_namespace,
    )
