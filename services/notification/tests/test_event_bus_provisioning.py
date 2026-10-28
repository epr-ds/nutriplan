"""NTF-704: the notification event bus consumer groups are provisioned per environment."""

from __future__ import annotations

import redis

from app.core.config import Settings
from app.events.provisioning import provision_event_bus

ORDER_STREAM = "commerce.order-events"


def test_provision_event_bus_ensures_the_configured_consumer_group() -> None:
    """NTF-704: provisioning creates the bus consumer group for the configured stream."""
    settings = Settings(
        environment="staging",
        event_bus_url="redis://redis:6379/0",
        order_event_stream=ORDER_STREAM,
        consumer_group="notification",
        consumer_name="notification-1",
    )
    provision_event_bus(settings)

    client = redis.Redis.from_url("redis://redis:6379/0", decode_responses=True)
    groups = client.xinfo_groups(name=ORDER_STREAM)
    assert any(group.get("name") == "notification" for group in groups)