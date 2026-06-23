"""A small key-value store seam for the AI service (AIA-105).

The response cache and the token-budget guard both need the same handful of operations
against a shared, expiring store. This package exposes that as the
:class:`~app.kv.store.KeyValueStore` port with two adapters -- an in-process one for
dev/CI/tests and a Redis one for production -- so neither caller depends on a driver or a
running server. :func:`build_key_value_store` chooses the backend from configuration.
"""

from app.kv.factory import build_key_value_store
from app.kv.memory import InMemoryKeyValueStore
from app.kv.redis_store import RedisKeyValueStore
from app.kv.store import Clock, KeyValueStore

__all__ = [
    "Clock",
    "InMemoryKeyValueStore",
    "KeyValueStore",
    "RedisKeyValueStore",
    "build_key_value_store",
]
