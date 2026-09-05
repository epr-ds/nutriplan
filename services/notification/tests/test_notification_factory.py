"""The factory: one place decides which store backs the service."""

from __future__ import annotations

from app.adapters.factory import (
    build_deduplication_store,
    build_idempotency_window,
    build_notification_recorder,
    build_notification_repository,
    build_retention_policy,
)
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.redis_deduplication_store import RedisDeduplicationStore
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.core.config import Settings
from app.domain.repositories import DeduplicationStore, NotificationRepository


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


# -- the deduplication store (NTF-103) -------------------------------------------


def test_without_a_redis_url_the_dedupe_store_is_in_process() -> None:
    assert isinstance(build_deduplication_store(_settings()), InMemoryDeduplicationStore)


def test_with_a_redis_url_the_dedupe_store_is_redis_backed() -> None:
    store = build_deduplication_store(_settings(redis_url="redis://redis:6379/0"))

    assert isinstance(store, RedisDeduplicationStore)


def test_both_dedupe_adapters_satisfy_the_port() -> None:
    for settings in (_settings(), _settings(redis_url="redis://redis:6379/0")):
        assert isinstance(build_deduplication_store(settings), DeduplicationStore)


def test_the_idempotency_window_comes_from_configuration() -> None:
    window = build_idempotency_window(_settings(dedupe_ttl_seconds=300, dedupe_claim_seconds=9))

    assert window.ttl_seconds == 300
    assert window.provisional == 9


def test_the_dedupe_store_follows_the_notification_store_onto_the_same_backend() -> None:
    """Split backends would be worse than no dedupe at all.

    A claim living where the notifications do not would suppress replays on behalf of
    records the reading process cannot see, so the user would silently lose them.
    """
    configured = _settings(redis_url="redis://redis:6379/0")

    assert isinstance(build_notification_repository(configured), RedisNotificationRepository)
    assert isinstance(build_deduplication_store(configured), RedisDeduplicationStore)
    assert isinstance(build_notification_repository(_settings()), InMemoryNotificationRepository)
    assert isinstance(build_deduplication_store(_settings()), InMemoryDeduplicationStore)


def test_the_dedupe_store_shares_the_configured_namespace() -> None:
    store = build_deduplication_store(
        _settings(redis_url="redis://redis:6379/0", redis_namespace="staging")
    )

    assert store._keys.prefix.startswith("staging:")


def test_the_recorder_is_built_from_both_ports() -> None:
    recorder = build_notification_recorder(_settings())

    assert isinstance(recorder.repository, InMemoryNotificationRepository)
    assert isinstance(recorder._deduplication, InMemoryDeduplicationStore)
