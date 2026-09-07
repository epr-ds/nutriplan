"""Pick the notification store backend from configuration.

One place maps ``NOTIFICATION_REDIS_URL`` onto a concrete store: set it and notifications
live in Redis, shared by every replica; leave it blank and an in-process store is used,
which is correct for dev, CI, and a single throwaway container but shares nothing between
processes. That is exactly the condition ``/health/ready`` reports as a warning outside
production and a hard failure inside it (NTF-101), so the two decisions stay consistent.

The retention policy is built from settings here as well, so both adapters are constructed
with the same window and neither can quietly disagree with the other.

The same applies to the deduplication store (NTF-103): it follows ``NOTIFICATION_REDIS_URL``
onto the same backend as the notification store, because a dedupe claim that lives somewhere
the notifications do not is worse than no dedupe at all -- it would suppress replays on
behalf of records another process cannot see.
"""

from __future__ import annotations

from app.adapters.idempotency import IdempotencyWindow
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.in_memory_preferences_repository import InMemoryPreferencesRepository
from app.adapters.keys import NotificationKeys
from app.adapters.redis_deduplication_store import RedisDeduplicationStore
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.adapters.redis_preferences_repository import RedisPreferencesRepository
from app.adapters.retention import RetentionPolicy
from app.application.notification_recorder import NotificationRecorder
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.domain.repositories import (
    DeduplicationStore,
    NotificationRepository,
    PreferencesRepository,
)


def build_retention_policy(settings: Settings | None = None) -> RetentionPolicy:
    """Return the configured age + length bounds for the feed."""
    settings = settings or default_settings
    return RetentionPolicy(
        ttl_seconds=settings.feed_ttl_seconds,
        max_entries=settings.feed_max_entries,
    )


def build_idempotency_window(settings: Settings | None = None) -> IdempotencyWindow:
    """Return the configured replay window and provisional claim length."""
    settings = settings or default_settings
    return IdempotencyWindow(
        ttl_seconds=settings.dedupe_ttl_seconds,
        provisional_seconds=settings.dedupe_claim_seconds,
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


def build_deduplication_store(settings: Settings | None = None) -> DeduplicationStore:
    """Return a Redis-backed dedupe store when a URL is configured, else an in-process one."""
    settings = settings or default_settings
    window = build_idempotency_window(settings)
    url = settings.redis_url.strip()
    if url:
        return RedisDeduplicationStore.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
            window=window,
        )
    return InMemoryDeduplicationStore(window=window)


def build_preferences_repository(settings: Settings | None = None) -> PreferencesRepository:
    """Return a Redis-backed preferences store when a URL is configured, else an in-process one."""
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisPreferencesRepository.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
        )
    return InMemoryPreferencesRepository()


def build_notification_recorder(settings: Settings | None = None) -> NotificationRecorder:
    """Return the idempotent write path event consumers should use (NTF-201/202)."""
    settings = settings or default_settings
    return NotificationRecorder(
        build_notification_repository(settings),
        build_deduplication_store(settings),
        build_preferences_repository(settings),
    )
