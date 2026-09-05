"""Pick the notification store backend from configuration.

One place maps ``NOTIFICATION_REDIS_URL`` onto a concrete store: set it and notifications
live in Redis, shared by every replica; leave it blank and an in-process store is used,
which is correct for dev, CI, and a single throwaway container but shares nothing between
processes. That is exactly the condition ``/health/ready`` reports as a warning outside
production and a hard failure inside it (NTF-101), so the two decisions stay consistent.

The retention policy is built from settings here as well, so both adapters are constructed
with the same window and neither can quietly disagree with the other.
"""

from __future__ import annotations

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.keys import NotificationKeys
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.adapters.retention import RetentionPolicy
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.domain.repositories import NotificationRepository


def build_retention_policy(settings: Settings | None = None) -> RetentionPolicy:
    """Return the configured age + length bounds for the feed."""
    settings = settings or default_settings
    return RetentionPolicy(
        ttl_seconds=settings.feed_ttl_seconds,
        max_entries=settings.feed_max_entries,
    )


def build_notification_repository(settings: Settings | None = None) -> NotificationRepository:
    """Return a Redis-backed store when a URL is configured, else an in-process one."""
    settings = settings or default_settings
    policy = build_retention_policy(settings)
    url = settings.redis_url.strip()
    if url:
        return RedisNotificationRepository.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
            policy=policy,
        )
    return InMemoryNotificationRepository(policy=policy)
