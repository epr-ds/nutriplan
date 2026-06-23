"""Response caching for the AI service (AIA-105, AC1).

Repeated AI requests should be cheap, so a completion is cached against a *normalized*
form of its request (model, sampling settings, messages, and any response-format schema)
under a configurable TTL. The cache sits behind the :class:`~app.kv.store.KeyValueStore`
port, so it is backed by Redis in production and an in-process store in tests, and it is
checked before any budget is charged so a hit is free.
"""

from app.cache.cache import ResponseCache
from app.cache.factory import build_response_cache
from app.cache.keys import cache_key, normalize_request

__all__ = [
    "ResponseCache",
    "build_response_cache",
    "cache_key",
    "normalize_request",
]
