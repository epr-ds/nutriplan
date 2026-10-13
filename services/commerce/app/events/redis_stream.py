"""The Redis-Streams-backed :class:`~app.events.publisher.EventPublisher` adapter (COM-109).

This is the only module that knows about the ``redis`` driver, imported lazily in :meth:`from_url`
so the package imports cleanly wherever Redis is neither installed nor running (tests inject a
duck-typed client instead). Events are appended to a Redis *stream* (``XADD``) rather than published
over pub/sub so they are durable: the P5 notification service can consume them with a consumer group
even if it was offline when the event was produced. The envelope travels as a single JSON
``payload`` field.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.domain.events import DomainEvent
from app.events.envelope import to_envelope


class RedisStreamLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def xadd(self, name: str, fields: dict[str, str]) -> Any: ...


class RedisStreamEventPublisher:
    """Publish order events to a Redis stream via ``XADD``."""

    def __init__(self, client: RedisStreamLike, *, stream: str) -> None:
        self._client = client
        self._stream = stream

    @classmethod
    def from_url(cls, url: str, *, stream: str) -> RedisStreamEventPublisher:
        """Build a publisher from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        return cls(redis.Redis.from_url(url, decode_responses=True), stream=stream)

    def publish(self, event: DomainEvent) -> None:
        envelope = to_envelope(event)
        self._client.xadd(self._stream, {"payload": json.dumps(envelope)})
