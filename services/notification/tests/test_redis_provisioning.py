"""NTF-703: the notification runtime provisions its Redis persistence from settings."""

from __future__ import annotations

from app.adapters.factory import provision_redis
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.core.config import Settings


def test_provision_redis_provisions_the_durable_store_when_configured() -> None:
    """NTF-703: an environment with a Redis URL provisions the durable persistence store."""
    settings = Settings(environment="staging", redis_url="redis://localhost:6379/0")
    store = provision_redis(settings)
    assert isinstance(store, RedisNotificationRepository)


def test_provision_redis_falls_back_to_the_in_process_store_when_unconfigured() -> None:
    """NTF-703: an unconfigured environment provisions the in-process store (dev/CI)."""
    settings = Settings(environment="development")
    store = provision_redis(settings)
    assert isinstance(store, InMemoryNotificationRepository)
