"""Pick the key-value store backend from configuration.

One place maps ``AI_REDIS_URL`` to a concrete store: set it and the cache and budget
counters live in Redis (shared across instances); leave it blank and an in-process store
is used, which is correct for dev/CI and a single replica but does not share state between
processes. The choice is invisible above the port.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.kv.memory import InMemoryKeyValueStore
from app.kv.redis_store import RedisKeyValueStore
from app.kv.store import KeyValueStore


def build_key_value_store(settings: Settings | None = None) -> KeyValueStore:
    """Return a Redis-backed store when ``AI_REDIS_URL`` is set, else an in-process one."""
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisKeyValueStore.from_url(url)
    return InMemoryKeyValueStore()
