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
where a Redis service container is always present. :func:`dedupe_store` and :func:`recorder`
do the same for NTF-103's idempotency store and the write path built on top of it.
:func:`event_bus` does it once more for NTF-201's consumer adapters, where the stake is
higher still: an in-process consumer that forgot to redeliver an unacked message would make
the whole at-least-once framework pass in CI and lose events in production.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from app.adapters.idempotency import IdempotencyWindow
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.in_memory_order_progress import InMemoryOrderProgressStore
from app.adapters.in_memory_preferences_repository import InMemoryPreferencesRepository
from app.adapters.keys import NotificationKeys
from app.adapters.redis_deduplication_store import RedisDeduplicationStore
from app.adapters.redis_notification_repository import RedisNotificationRepository
from app.adapters.redis_order_progress import RedisOrderProgressStore
from app.adapters.redis_preferences_repository import RedisPreferencesRepository
from app.adapters.retention import RetentionPolicy
from app.application.notification_recorder import NotificationRecorder
from app.application.order_status_consumer import OrderStatusConsumer
from app.domain.notification import Notification
from app.domain.repositories import (
    DeduplicationStore,
    NotificationRepository,
    OrderProgressStore,
    PreferencesRepository,
)
from app.events.consumer import EventConsumer
from app.events.memory import InMemoryEventConsumer
from app.events.redis_stream import PAYLOAD_FIELD, RedisStreamEventConsumer

PRESERVED = {"NOTIFICATION_TEST_REDIS_URL", "NOTIFICATION_OPENAPI_SPEC"}
"""Harness inputs, not service configuration -- they must survive the isolation fixture.

Both merely match the service's env prefix. Stripping ``NOTIFICATION_OPENAPI_SPEC`` would
make the contract tests silently skip whenever the spec is mounted somewhere the
walk-up-the-parents search can't find it, which reads as "no contract drift" rather than
"the gate never ran".
"""

TEST_REDIS_URL = os.getenv("NOTIFICATION_TEST_REDIS_URL", "").strip()
"""A live Redis to exercise the real adapter against; empty means "skip those tests"."""

TEST_POLICY = RetentionPolicy(ttl_seconds=3_600, max_entries=100)
"""A short, small window so retention is observable without waiting or writing thousands."""

TEST_WINDOW = IdempotencyWindow(ttl_seconds=600, provisional_seconds=60)
"""Long enough that nothing lapses mid-test; expiry tests pass their own short window."""

TEST_CONSUMER_GROUP = "notification-test"
TEST_CONSUMER_NAME = "notification-test-1"
"""Group and consumer names for the eventing suite; the stream is unique per test."""

DedupeStoreFactory = Callable[..., DeduplicationStore]


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


def isolated_stream() -> str:
    """A stream name unique to one test.

    Streams need this more than the key-value tests do: a consumer group carries an offset
    and a pending list, so two tests sharing a stream would not merely see each other's data,
    they would consume each other's messages and each would report the other's bug.
    """
    return f"nt-test-stream-{uuid.uuid4().hex[:12]}"


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


@pytest.fixture(params=["memory", "redis"])
def dedupe_store(request: pytest.FixtureRequest) -> Iterator[DedupeStoreFactory]:
    """A *factory* for dedupe stores, parametrized over both adapters.

    A factory rather than a ready-made store because the interesting property of an
    idempotency claim is when it lapses, and that means a test has to choose the window it
    runs against. The factory keeps the backend and its cleanup here while leaving the
    window to the test.
    """
    if request.param == "memory":

        def build_memory(**kwargs: object) -> DeduplicationStore:
            kwargs.setdefault("window", TEST_WINDOW)
            return InMemoryDeduplicationStore(**kwargs)  # type: ignore[arg-type]

        yield build_memory
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()

    def build_redis(**kwargs: object) -> DeduplicationStore:
        kwargs.pop("clock", None)  # a real server keeps its own time
        return RedisDeduplicationStore(
            client,  # type: ignore[arg-type]
            keys=NotificationKeys(namespace=namespace),
            window=kwargs.pop("window", TEST_WINDOW),  # type: ignore[arg-type]
        )

    try:
        yield build_redis
    finally:
        drop_namespace(client, namespace)
        client.close()


@pytest.fixture(params=["memory", "redis"])
def preferences_repository(request: pytest.FixtureRequest) -> Iterator[PreferencesRepository]:
    """One preferences store per adapter, so every test using it is a parity contract."""
    if request.param == "memory":
        yield InMemoryPreferencesRepository()
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()
    try:
        yield RedisPreferencesRepository(
            client,  # type: ignore[arg-type]
            keys=NotificationKeys(namespace=namespace),
        )
    finally:
        drop_namespace(client, namespace)
        client.close()


@pytest.fixture(params=["memory", "redis"])
def recorder(request: pytest.FixtureRequest) -> Iterator[NotificationRecorder]:
    """The idempotent write path, with both of its ports on the same backend.

    Pairing them matters: a dedupe claim living somewhere its notifications do not would
    suppress replays on behalf of records the reader cannot see, so the fixture never mixes
    an in-memory claim with a Redis record.
    """
    if request.param == "memory":
        yield NotificationRecorder(
            InMemoryNotificationRepository(policy=TEST_POLICY),
            InMemoryDeduplicationStore(window=TEST_WINDOW),
        )
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()
    try:
        yield NotificationRecorder(
            redis_repository(client, namespace=namespace),
            RedisDeduplicationStore(
                client,  # type: ignore[arg-type]
                keys=NotificationKeys(namespace=namespace),
                window=TEST_WINDOW,
            ),
        )
    finally:
        drop_namespace(client, namespace)
        client.close()


@dataclass
class EventBus:
    """A consumer plus the means to put something on the stream it reads.

    The consumer port is read-only by design -- publishing is commerce's job, not this
    service's -- so a test that needs an event to exist has to reach past the port to
    whichever backend it is running against. Pairing the two here keeps that asymmetry in one
    place, and lets a single test body run against both adapters unchanged.
    """

    consumer: EventConsumer
    _publish: Callable[[str], str]

    def publish(self, envelope: Mapping[str, Any] | str) -> str:
        """Append an envelope to the stream exactly as the commerce publisher does."""
        payload = envelope if isinstance(envelope, str) else json.dumps(dict(envelope))
        return self._publish(payload)

    def publish_all(self, *envelopes: Mapping[str, Any] | str) -> tuple[str, ...]:
        """Append several envelopes in order, returning their entry ids."""
        return tuple(self.publish(envelope) for envelope in envelopes)


@pytest.fixture(params=["memory", "redis"])
def event_bus(request: pytest.FixtureRequest) -> Iterator[EventBus]:
    """One consumer per adapter, its group already created, with a way to publish to it.

    The group is created before the test body runs because that is the order a worker starts
    in, and because a group created at ``$`` would otherwise skip everything the test
    published first -- correct behaviour that would look like a broken fixture. The one test
    that cares about that offset builds its own consumer instead.
    """
    if request.param == "memory":
        consumer = InMemoryEventConsumer()
        consumer.ensure_group()
        yield EventBus(consumer, consumer.publish)
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    stream = isolated_stream()
    try:
        consumer = RedisStreamEventConsumer(
            client,  # type: ignore[arg-type]
            stream=stream,
            group=TEST_CONSUMER_GROUP,
            consumer=TEST_CONSUMER_NAME,
        )
        consumer.ensure_group()

        def publish(payload: str) -> str:
            return str(client.xadd(stream, {PAYLOAD_FIELD: payload}))

        yield EventBus(consumer, publish)
    finally:
        client.delete(stream)
        client.close()


OrderProgressFactory = Callable[..., OrderProgressStore]


@pytest.fixture(params=["memory", "redis"])
def order_progress(request: pytest.FixtureRequest) -> Iterator[OrderProgressFactory]:
    """A *factory* for order-progress stores, parametrized over both adapters (NTF-202).

    A factory for the same reason ``dedupe_store`` is one: the interesting property of the
    mark is what happens when it expires, and that means the test has to choose the window.
    """
    if request.param == "memory":

        def build_memory(**kwargs: object) -> OrderProgressStore:
            kwargs.setdefault("ttl_seconds", 3_600)
            return InMemoryOrderProgressStore(**kwargs)  # type: ignore[arg-type]

        yield build_memory
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()

    def build_redis(**kwargs: object) -> OrderProgressStore:
        kwargs.pop("clock", None)  # a real server keeps its own time
        return RedisOrderProgressStore(
            client,  # type: ignore[arg-type]
            keys=NotificationKeys(namespace=namespace),
            ttl_seconds=kwargs.pop("ttl_seconds", 3_600),  # type: ignore[arg-type]
        )

    try:
        yield build_redis
    finally:
        drop_namespace(client, namespace)
        client.close()


@dataclass
class OrderConsumerHarness:
    """The NTF-202 consumer with the stores behind it left reachable.

    A consumer's whole output is a side effect, so a test needs to read the store to see
    what it did. Bundling the two here keeps every assertion going through the same backend
    the consumer wrote to -- the mistake that would make an in-memory test pass while the
    Redis one silently asserted nothing.
    """

    consumer: OrderStatusConsumer
    repository: NotificationRepository
    progress: OrderProgressStore
    preferences: PreferencesRepository

    def feed(self, user_id: uuid.UUID) -> list[Notification]:
        """Everything recorded for a user, newest first."""
        return self.repository.list_for_user(user_id)

    def types(self, user_id: uuid.UUID) -> list[str]:
        """Just the notification types in the user's feed, for readable assertions."""
        return [n.type.value for n in self.feed(user_id)]


@pytest.fixture(params=["memory", "redis"])
def order_consumer(request: pytest.FixtureRequest) -> Iterator[OrderConsumerHarness]:
    """The order-status consumer wired to one backend, with its stores exposed."""
    if request.param == "memory":
        repository: NotificationRepository = InMemoryNotificationRepository(policy=TEST_POLICY)
        preferences: PreferencesRepository = InMemoryPreferencesRepository()
        progress: OrderProgressStore = InMemoryOrderProgressStore(ttl_seconds=3_600)
        recorder = NotificationRecorder(
            repository,
            InMemoryDeduplicationStore(window=TEST_WINDOW),
            preferences,
        )
        yield OrderConsumerHarness(
            OrderStatusConsumer(recorder, progress), repository, progress, preferences
        )
        return

    import redis

    client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    try:
        repository = redis_repository(client, namespace=namespace)
        preferences = RedisPreferencesRepository(client, keys=keys)  # type: ignore[arg-type]
        progress = RedisOrderProgressStore(client, keys=keys, ttl_seconds=3_600)  # type: ignore[arg-type]
        recorder = NotificationRecorder(
            repository,
            RedisDeduplicationStore(client, keys=keys, window=TEST_WINDOW),  # type: ignore[arg-type]
            preferences,
        )
        yield OrderConsumerHarness(
            OrderStatusConsumer(recorder, progress), repository, progress, preferences
        )
    finally:
        drop_namespace(client, namespace)
        client.close()
