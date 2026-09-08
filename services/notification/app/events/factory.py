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

from collections.abc import Mapping

from app.adapters.factory import build_notification_recorder, build_order_progress_store
from app.adapters.keys import NotificationKeys
from app.application.dead_letter_replay import DeadLetterReplayer
from app.application.order_status_consumer import HANDLED_EVENT_TYPES, OrderStatusConsumer
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.backoff import RetrySchedule
from app.events.consumer import EventConsumer, EventHandler
from app.events.dead_letter import DeadLetterQueue, InMemoryDeadLetterQueue
from app.events.dispatcher import EventDispatcher
from app.events.memory import InMemoryEventConsumer
from app.events.metrics import EventMetrics
from app.events.redis_dead_letter import RedisDeadLetterQueue
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


def build_retry_schedule(settings: Settings | None = None) -> RetrySchedule:
    """Return the configured backoff between retries of a failing delivery (NTF-204).

    The base is the reclaim idle window rather than a setting of its own -- see
    :mod:`app.events.backoff` for why a retry cannot safely happen sooner than that.
    """
    settings = settings or default_settings
    return RetrySchedule(
        base_ms=settings.event_reclaim_idle_ms,
        multiplier=settings.event_retry_multiplier,
        cap_ms=settings.event_retry_cap_ms,
        jitter=settings.event_retry_jitter,
    )


def build_dead_letter_queue(settings: Settings | None = None) -> DeadLetterQueue:
    """Return the durable queue parked events wait in, else an in-process one (NTF-204).

    Follows ``NOTIFICATION_REDIS_URL`` rather than the bus URL. The queue is *state*, not
    transport: it has to be readable by the DLQ CLI in a separate container from the worker
    that filled it, so it belongs wherever the rest of this service's state lives. Putting it
    on the bus Redis instead would work today -- one Redis backs both -- and would silently
    become unreachable the day those are split.
    """
    settings = settings or default_settings
    url = settings.redis_url.strip()
    if url:
        return RedisDeadLetterQueue.from_url(
            url,
            keys=NotificationKeys(namespace=settings.redis_namespace),
            max_entries=settings.dead_letter_max_entries,
            ttl_seconds=settings.dead_letter_ttl_seconds,
        )
    return InMemoryDeadLetterQueue(capacity=settings.dead_letter_max_entries)


def build_order_status_consumer(settings: Settings | None = None) -> OrderStatusConsumer:
    """Assemble the handler that turns order events into notifications (NTF-202)."""
    settings = settings or default_settings
    return OrderStatusConsumer(
        build_notification_recorder(settings),
        build_order_progress_store(settings),
    )


def build_event_dispatcher(
    settings: Settings | None = None,
    *,
    consumer: EventConsumer | None = None,
    registry: EventSchemaRegistry | None = None,
    dead_letters: DeadLetterQueue | None = None,
    handlers: Mapping[str, EventHandler] | None = None,
    schedule: RetrySchedule | None = None,
    metrics: EventMetrics | None = None,
) -> EventDispatcher:
    """Assemble the dispatcher, letting a caller substitute any single collaborator.

    NTF-201 built this with no handlers; NTF-202 registers the first. The order-status
    consumer is bound to both of Commerce's transition events -- ``order.confirmed`` for the
    ``pending -> confirmed`` move and ``order.status_changed`` for every other -- because
    COM-109 publishes one *or* the other, never both.

    ``order.created`` is deliberately left unregistered rather than handled-and-ignored. The
    dispatcher acks an event nothing is registered for, so the absence *is* the decision, and
    it is visible here in one place instead of being a ``return`` buried in a handler.
    """
    settings = settings or default_settings
    if handlers is None:
        order_status = build_order_status_consumer(settings)
        handlers = dict.fromkeys(HANDLED_EVENT_TYPES, order_status)
    return EventDispatcher(
        consumer or build_event_consumer(settings),
        registry=registry or default_registry(),
        dead_letters=dead_letters or build_dead_letter_queue(settings),
        handlers=handlers,
        max_attempts=settings.event_max_delivery_attempts,
        schedule=schedule or build_retry_schedule(settings),
        metrics=metrics,
    )


def build_dead_letter_replayer(
    settings: Settings | None = None, *, dispatcher: EventDispatcher | None = None
) -> DeadLetterReplayer:
    """Assemble the replay path the DLQ CLI drives (NTF-204).

    The replayer and the dispatcher must share one queue instance, or the replayer would read
    from a queue the dispatcher never fills. Pulling it back off the dispatcher rather than
    building a second one makes that impossible to get wrong.
    """
    settings = settings or default_settings
    dispatcher = dispatcher or build_event_dispatcher(settings)
    return DeadLetterReplayer(dispatcher.dead_letters, dispatcher)
