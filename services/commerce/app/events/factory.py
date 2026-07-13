"""Choose the domain-event publisher backend from configuration (COM-109).

Set ``COMMERCE_EVENT_BUS_URL`` and order events are appended to a Redis stream shared with the
notification service; leave it blank and an in-process publisher is used, which is correct for
dev/CI and a single replica but does not leave the process. Either backend is wrapped so a transport
failure never fails the order write. The choice is invisible above the port.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.memory import InMemoryEventPublisher
from app.events.publisher import EventPublisher
from app.events.redis_stream import RedisStreamEventPublisher
from app.events.resilient import ResilientEventPublisher


def build_event_publisher(settings: Settings | None = None) -> EventPublisher:
    """Return a Redis-stream publisher when ``COMMERCE_EVENT_BUS_URL`` is set, else in-process.

    Whichever backend is chosen is wrapped in a
    :class:`~app.events.resilient.ResilientEventPublisher` so a broker outage degrades to a logged
    miss rather than a failed order write.
    """
    settings = settings or default_settings
    url = settings.event_bus_url.strip()
    inner: EventPublisher
    if url:
        inner = RedisStreamEventPublisher.from_url(url, stream=settings.event_stream)
    else:
        inner = InMemoryEventPublisher()
    return ResilientEventPublisher(inner)
