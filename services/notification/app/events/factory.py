"""Choose the event-consumer backend from configuration (NTF-201).

Mirrors :mod:`app.adapters.factory` and commerce's :mod:`app.events.factory`: one place maps
settings onto concrete objects, so nothing above the seam decides what it is talking to.

``NOTIFICATION_EVENT_BUS_URL`` selects Redis Streams; blank falls back to
``NOTIFICATION_REDIS_URL`` (one Redis backs both in every environment we run today, and
splitting them stays a config change). With neither set, an in-process consumer is used --
correct for dev and CI, and reported by ``/health/ready`` as a warning outside production and
a hard failure inside it, so nobody ships it by accident.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.consumer import EventConsumer
from app.events.dead_letter import DeadLetterSink, LoggingDeadLetterSink
from app.events.dispatcher import EventDispatcher
from app.events.memory import InMemoryEventConsumer
from app.events.redis_stream import RedisStreamEventConsumer
from app.events.registry import EventSchemaRegistry, default_registry


def build_event_consumer(settings: Settings | None = None) -> EventConsumer:
    """Return a Redis Streams consumer when a bus URL is configured, else in-process."""
    settings = settings or default_settings
    url = settings.effective_event_bus_url
    if url:
        return RedisStreamEventConsumer.from_url(
            url,
            stream=settings.order_event_stream,
            group=settings.consumer_group,
            consumer=settings.consumer_name,
        )
    return InMemoryEventConsumer()


def build_dead_letter_sink(settings: Settings | None = None) -> DeadLetterSink:
    """Return the sink for permanently-failed events.

    A logging sink today; NTF-204 replaces it with a durable queue and a replay path. It is
    built through the factory even while there is only one implementation, and takes the
    settings it does not yet read, so swapping it is a one-line change here rather than a
    hunt through the call sites.
    """
    return LoggingDeadLetterSink()


def build_event_dispatcher(
    settings: Settings | None = None,
    *,
    consumer: EventConsumer | None = None,
    registry: EventSchemaRegistry | None = None,
    dead_letters: DeadLetterSink | None = None,
) -> EventDispatcher:
    """Assemble the dispatcher, letting a caller substitute any single collaborator.

    The dispatcher is built with **no handlers**. NTF-201 is the framework and the schema
    registry; deciding what an order event should turn into is NTF-202's job, and it
    registers its handlers on the returned dispatcher. Until it does, the service consumes
    the stream, validates every event against the registry, and acknowledges each one without
    acting -- which is exactly what a framework with nothing plugged into it should do.
    """
    settings = settings or default_settings
    return EventDispatcher(
        consumer or build_event_consumer(settings),
        registry=registry or default_registry(),
        dead_letters=dead_letters or build_dead_letter_sink(settings),
        max_attempts=settings.event_max_delivery_attempts,
    )
