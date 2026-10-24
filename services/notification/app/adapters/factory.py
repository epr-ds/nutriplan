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

import logging

from app.adapters.apns_adapter import build_apns_adapter
from app.adapters.fcm_adapter import build_fcm_adapter
from app.adapters.idempotency import IdempotencyWindow
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.in_memory_device_token_repository import InMemoryDeviceTokenRepository
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.in_memory_order_progress import InMemoryOrderProgressStore
from app.adapters.in_memory_preferences_repository import InMemoryPreferencesRepository
from app.adapters.in_memory_push_receipt_store import InMemoryPushReceiptStore
from app.adapters.keys import NotificationKeys
from app.adapters.push_gateways import ApnsPushGateway, FcmPushGateway
from app.adapters.redis_deduplication_store import RedisDeduplicationStore
from app.adapters.redis_device_token_repository import RedisDeviceTokenRepository
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.adapters.redis_order_progress import RedisOrderProgressStore
from app.adapters.redis_preferences_repository import RedisPreferencesRepository
from app.adapters.redis_push_receipt_store import RedisPushReceiptStore
from app.adapters.retention import RetentionPolicy
from app.application.devices import DeviceRegistrationService
from app.application.notification_recorder import NotificationRecorder
from app.application.push_delivery import PushDelivery
from app.application.templates import build_default_catalog
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.domain.enums import DevicePlatform
from app.domain.push import PushGateway
from app.domain.repositories import (
    DeduplicationStore,
    DeviceTokenRepository,
    NotificationRepository,
    OrderProgressStore,
    PreferencesRepository,
    PushReceiptStore,
)

logger = logging.getLogger(__name__)


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


def build_device_token_repository(settings: Settings | None = None) -> DeviceTokenRepository:
    """Return a Redis-backed device registry when a URL is configured, else in-process."""
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisDeviceTokenRepository.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
        )
    return InMemoryDeviceTokenRepository()


def build_order_progress_store(settings: Settings | None = None) -> OrderProgressStore:
    """Return the order-progress mark backing the out-of-order guard (NTF-202)."""
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisOrderProgressStore.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
            ttl_seconds=settings.order_progress_ttl_seconds,
        )
    return InMemoryOrderProgressStore(ttl_seconds=settings.order_progress_ttl_seconds)


def build_notification_recorder(settings: Settings | None = None) -> NotificationRecorder:
    """Return the idempotent write path event consumers should use (NTF-201/202)."""
    settings = settings or default_settings
    return NotificationRecorder(
        build_notification_repository(settings),
        build_deduplication_store(settings),
        build_preferences_repository(settings),
    )


# Phase 5: Push delivery


def build_push_gateways(settings: Settings | None = None) -> dict[DevicePlatform, PushGateway]:
    """Build the configured provider gateways, keyed by the platform they reach (NTF-303).

    An absent or half-configured provider is simply left out: a deployment with only FCM
    configured still pushes to Android devices, and the delivery path selects a device on a
    reachable platform rather than failing the user outright.
    """
    settings = settings or default_settings
    if not settings.push_enabled:
        return {}

    gateways: dict[DevicePlatform, PushGateway] = {}
    if settings.fcm_configured:
        try:
            gateways[DevicePlatform.ANDROID] = FcmPushGateway(build_fcm_adapter(settings))
        except Exception as exc:
            logger.warning("fcm.gateway_build_failed error=%s", exc)
    if settings.apns_configured:
        try:
            gateways[DevicePlatform.IOS] = ApnsPushGateway(build_apns_adapter(settings))
        except Exception as exc:
            logger.warning("apns.gateway_build_failed error=%s", exc)
    return gateways


def build_push_receipt_store(settings: Settings | None = None) -> PushReceiptStore:
    """Return the per-device receipt store backing fan-out (NTF-305).

    It follows ``NOTIFICATION_REDIS_URL`` onto the same backend as the notifications, because
    a receipt living somewhere the notification does not is worse than no receipt: the fan-out
    would think a device had already been tried (or not) based on state no other replica can
    see, and either skip a device or send it a second push.
    """
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisPushReceiptStore.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
            ttl_seconds=settings.feed_ttl_seconds,
        )
    return InMemoryPushReceiptStore(ttl_seconds=settings.feed_ttl_seconds)


def build_push_delivery(
    settings: Settings | None = None,
    *,
    notifications: NotificationRepository,
) -> PushDelivery | None:
    """Assemble the send-and-record path over the *caller's* notification store (NTF-303/305).

    The repository is passed in rather than rebuilt because the in-process store keeps its
    state inside the object: a delivery path reading a different instance than the recorder
    wrote to would report every notification as expired in dev and CI. ``None`` means no
    provider is configured, so the caller should not attempt delivery at all.
    """
    settings = settings or default_settings
    gateways = build_push_gateways(settings)
    if not gateways:
        return None
    return PushDelivery(
        notifications,
        DeviceRegistrationService(build_device_token_repository(settings)),
        gateways,
        build_push_receipt_store(settings),
        max_attempts=settings.push_max_attempts,
        backoff_seconds=settings.push_retry_backoff_ms / 1000.0,
        backoff_multiplier=settings.push_retry_multiplier,
        preferences=build_preferences_repository(settings),
        templates=build_default_catalog(),
    )


# Phase 5: Meal reminder consumer builder


def build_meal_reminder_consumer(
    settings: Settings | None = None,
) -> "MealReminderConsumer":  # noqa: F821
    """Assemble the meal reminder handler."""
    from app.application.meal_reminder_consumer import MealReminderConsumer

    settings = settings or default_settings
    recorder = build_notification_recorder(settings)
    return MealReminderConsumer(
        recorder,
        push=build_push_delivery(settings, notifications=recorder.repository),
    )


# Phase 5: Plan ending consumer builder


def build_plan_ending_consumer(
    settings: Settings | None = None,
) -> "PlanEndingConsumer":  # noqa: F821
    """Assemble the plan ending handler."""
    from app.application.plan_ending_consumer import PlanEndingConsumer

    settings = settings or default_settings
    recorder = build_notification_recorder(settings)
    return PlanEndingConsumer(
        recorder,
        push=build_push_delivery(settings, notifications=recorder.repository),
    )
