"""Event-bus provisioning (NTF-704)."""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.redis_stream import RedisStreamEventConsumer


def provision_event_bus(settings: Settings | None = None) -> None:
    """Provision the event-bus consumer groups from configuration (NTF-704).

    A configured bus URL means durable Redis streams, so provisioning creates the consumer
    group at the stream's end for the configured stream/group. An unconfigured backend (the
    in-process bus) has nothing to provision. ``ensure_group`` tolerates the group already
    existing, so redeploys re-provisioning the same group are no-ops.
    """
    settings = settings or default_settings
    url = settings.effective_event_bus_url
    if not url:
        return
    consumer = RedisStreamEventConsumer.from_url(
        url,
        stream=settings.order_event_stream,
        group=settings.consumer_group,
        consumer=settings.consumer_name,
    )
    consumer.ensure_group()
