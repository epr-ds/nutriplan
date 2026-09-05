"""Shared fixtures for the notification suite.

The service is configured entirely through ``NOTIFICATION_``-prefixed environment
variables, which means an ambient value (compose sets ``NOTIFICATION_ENVIRONMENT=test``,
a developer may have a shell export) would otherwise silently change what the tests
observe. Every test builds its own :class:`Settings`, so the ambient values are stripped
first and the suite asserts on the code's real defaults in every environment.

``NOTIFICATION_TEST_REDIS_URL`` is deliberately preserved: it is a *harness* variable
that points the store and probe suites at a live server, not service configuration.

The :func:`repository` fixture is the important one here. It is parametrized over **both**
store adapters, so every test written against it is a contract both implementations must
satisfy -- which is the only way the in-memory store stays a faithful stand-in rather than
drifting into a convenient fiction. The Redis leg skips locally and is *required* under CI,
where a Redis service container is always present.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.keys import NotificationKeys
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.adapters.retention import RetentionPolicy
from app.domain.repositories import NotificationRepository

PRESERVED = {"NOTIFICATION_TEST_REDIS_URL"}

TEST_REDIS_URL = os.getenv("NOTIFICATION_TEST_REDIS_URL", "").strip()
"""A live Redis to exercise the real adapter against; empty means "skip those tests"."""

TEST_POLICY = RetentionPolicy(ttl_seconds=3_600, max_entries=100)
"""A short, small window so retention is observable without waiting or writing thousands."""


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient service configuration so each test controls its own settings."""
    for name in list(os.environ):
        if name.startswith("NOTIFICATION_") and name not in PRESERVED:
            monkeypatch.delenv(name, raising=False)


def require_redis_url() -> str:
    """Return the harness Redis URL, skipping locally but failing under CI.

    Skipping keeps the suite runnable on a laptop with no Redis; failing under CI stops the
    Redis half of the contract from being silently skipped in the one place it must run.
    """
    if TEST_REDIS_URL:
        return TEST_REDIS_URL
    if os.getenv("CI"):
        pytest.fail("NOTIFICATION_TEST_REDIS_URL must be set in CI so the Redis store is tested")
    return pytest.skip("set NOTIFICATION_TEST_REDIS_URL to exercise the Redis store")


@pytest.fixture
def redis_client() -> Iterator[object]:
    """A live redis-py client, closed at the end of the test."""
    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    try:
        yield client
    finally:
        client.close()


def redis_repository(
    client: object, *, namespace: str, **kwargs: object
) -> RedisNotificationRepository:
    """A Redis store confined to ``namespace``, so concurrent tests never collide."""
    return RedisNotificationRepository(
        client,  # type: ignore[arg-type]
        keys=NotificationKeys(namespace=namespace),
        policy=kwargs.pop("policy", TEST_POLICY),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def isolated_namespace() -> str:
    """A namespace unique to one test, so no cleanup can affect another."""
    return f"nt-test-{uuid.uuid4().hex[:12]}"


def drop_namespace(client: object, namespace: str) -> None:
    """Remove every key a test wrote, leaving the shared server clean."""
    for key in client.scan_iter(f"{namespace}:*"):  # type: ignore[attr-defined]
        client.delete(key)  # type: ignore[attr-defined]


@pytest.fixture(params=["memory", "redis"])
def repository(request: pytest.FixtureRequest) -> Iterator[NotificationRepository]:
    """One store per adapter, so every test using it is an adapter-parity contract."""
    if request.param == "memory":
        yield InMemoryNotificationRepository(policy=TEST_POLICY)
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()
    try:
        yield redis_repository(client, namespace=namespace)
    finally:
        drop_namespace(client, namespace)
        client.close()
