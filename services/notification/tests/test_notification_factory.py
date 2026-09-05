"""The factory: one place decides which store backs the service."""

from __future__ import annotations

from app.adapters.factory import build_notification_repository, build_retention_policy
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.core.config import Settings
from app.domain.repositories import NotificationRepository


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"environment": "test", "redis_url": ""}
    return Settings(**(defaults | overrides))  # type: ignore[arg-type]


def test_without_a_redis_url_the_store_is_in_process() -> None:
    # Correct for dev, CI, and a single throwaway container -- and exactly the state
    # /health/ready reports as a warning outside production and a failure inside it.
    assert isinstance(build_notification_repository(_settings()), InMemoryNotificationRepository)


def test_with_a_redis_url_the_store_is_redis_backed() -> None:
    # from_url does not connect, so this builds without a server running.
    store = build_notification_repository(_settings(redis_url="redis://redis:6379/0"))

    assert isinstance(store, RedisNotificationRepository)


def test_a_whitespace_only_url_is_treated_as_unset() -> None:
    assert isinstance(
        build_notification_repository(_settings(redis_url="   ")),
        InMemoryNotificationRepository,
    )


def test_both_adapters_satisfy_the_port() -> None:
    for settings in (_settings(), _settings(redis_url="redis://redis:6379/0")):
        store = build_notification_repository(settings)

        assert isinstance(store, NotificationRepository)


def test_the_retention_policy_comes_from_configuration() -> None:
    policy = build_retention_policy(_settings(feed_ttl_seconds=120, feed_max_entries=7))

    assert policy.ttl_seconds == 120
    assert policy.max_entries == 7


def test_the_default_window_is_thirty_days() -> None:
    policy = build_retention_policy(_settings())

    assert policy.ttl_seconds == 30 * 24 * 60 * 60
    assert policy.bounded is True


def test_the_namespace_reaches_the_redis_keys() -> None:
    store = build_notification_repository(
        _settings(redis_url="redis://redis:6379/0", redis_namespace="staging")
    )

    assert store._keys.prefix.startswith("staging:")


def test_both_stores_are_built_with_the_same_window() -> None:
    # If only one adapter honoured the configured window, the contract suite would pass
    # and production would quietly disagree with dev.
    settings = _settings(feed_ttl_seconds=90, feed_max_entries=3)

    memory = build_notification_repository(settings)
    redis_backed = build_notification_repository(
        _settings(feed_ttl_seconds=90, feed_max_entries=3, redis_url="redis://redis:6379/0")
    )

    assert memory._policy == redis_backed._policy == build_retention_policy(settings)
