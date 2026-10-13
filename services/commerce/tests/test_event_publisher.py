"""COM-109: the event-publisher adapters (Redis stream, resilient wrapper, factory).

No live Redis and no network: the Redis adapter is driven by a duck-typed fake client that records
``XADD`` calls (mirroring the AI service's ``test_kv_redis.py`` precedent), the resilient wrapper is
proven to swallow a raising inner while delegating on success, and the factory's backend selection
is checked by monkeypatching the Redis publisher so it never imports the driver or connects.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.events import OrderCreated
from app.events.envelope import SCHEMA_VERSION
from app.events.factory import build_event_publisher
from app.events.memory import InMemoryEventPublisher
from app.events.publisher import EventPublisher
from app.events.redis_stream import RedisStreamEventPublisher
from app.events.resilient import ResilientEventPublisher


def _event() -> OrderCreated:
    return OrderCreated(
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        occurred_at=datetime(2026, 7, 12, 21, 0, tzinfo=UTC),
    )


class _FakeRedis:
    """Records ``xadd`` calls the way redis-py would receive them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def xadd(self, name: str, fields: dict[str, str]) -> Any:
        self.calls.append((name, fields))
        return f"{len(self.calls)}-0"


# --------------------------------------------------------------------------- Redis stream adapter


def test_redis_publisher_xadds_the_envelope_as_json_payload():
    client = _FakeRedis()
    publisher = RedisStreamEventPublisher(client, stream="commerce.order-events")
    event = _event()

    publisher.publish(event)

    assert len(client.calls) == 1
    name, fields = client.calls[0]
    assert name == "commerce.order-events"
    assert set(fields) == {"payload"}
    payload = json.loads(fields["payload"])
    assert payload["schemaVersion"] == SCHEMA_VERSION
    assert payload["type"] == "order.created"
    assert payload["data"] == {"orderId": str(event.order_id), "userId": str(event.user_id)}


def test_redis_publisher_uses_the_configured_stream():
    client = _FakeRedis()

    RedisStreamEventPublisher(client, stream="custom.stream").publish(_event())

    assert client.calls[0][0] == "custom.stream"


# --------------------------------------------------------------------------- resilient wrapper


class _BoomPublisher:
    def publish(self, event: object) -> None:
        raise RuntimeError("bus is down")


def test_resilient_publisher_swallows_a_transport_error():
    publisher = ResilientEventPublisher(_BoomPublisher())

    # Must not raise: the order write already succeeded, a broker hiccup cannot fail the request.
    publisher.publish(_event())


def test_resilient_publisher_delegates_to_inner_on_success():
    inner = InMemoryEventPublisher()
    publisher = ResilientEventPublisher(inner)
    event = _event()

    publisher.publish(event)

    assert inner.published == [event]


def test_resilient_publisher_logs_the_failure(caplog: pytest.LogCaptureFixture):
    with caplog.at_level("ERROR"):
        ResilientEventPublisher(_BoomPublisher()).publish(_event())

    assert "Failed to publish domain event OrderCreated" in caplog.text


# --------------------------------------------------------------------------- factory selection


def test_factory_uses_in_memory_when_no_url():
    publisher = build_event_publisher(Settings(event_bus_url=""))

    assert isinstance(publisher, ResilientEventPublisher)
    assert isinstance(publisher._inner, InMemoryEventPublisher)


def test_factory_uses_redis_when_url_set(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}
    sentinel = InMemoryEventPublisher()

    class _FakePublisher:
        @classmethod
        def from_url(cls, url: str, *, stream: str) -> EventPublisher:
            captured["url"] = url
            captured["stream"] = stream
            return sentinel

    monkeypatch.setattr("app.events.factory.RedisStreamEventPublisher", _FakePublisher)

    publisher = build_event_publisher(
        Settings(event_bus_url="redis://cache:6379/0", event_stream="orders.v1")
    )

    assert isinstance(publisher, ResilientEventPublisher)
    assert publisher._inner is sentinel
    assert captured == {"url": "redis://cache:6379/0", "stream": "orders.v1"}


def test_factory_strips_blank_url_to_in_memory():
    # A whitespace-only URL must be treated as "unset", not a malformed Redis URL.
    publisher = build_event_publisher(Settings(event_bus_url="   "))

    assert isinstance(publisher._inner, InMemoryEventPublisher)
