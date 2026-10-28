"""NTF-704: the notification event bus is provisioned per environment."""

from __future__ import annotations

from app.core.config import Settings
from app.events.provisioning import provision_event_bus
from tests.conftest import TEST_REDIS_URL

ORDER_STREAM = "commerce.order-events"


def test_provision_event_bus_ensures_the_configured_consumer_group(redis_client) -> None:
    """NTF-704: provisioning creates the bus consumer group for the configured stream."""
    settings = Settings(
        environment="staging",
        event_bus_url=TEST_REDIS_URL,
        order_event_stream=ORDER_STREAM,
        consumer_group="notification",
        consumer_name="notification-1",
    )
    provision_event_bus(settings)

    groups = redis_client.xinfo_groups(name=ORDER_STREAM)
    assert any(group.get("name") == "notification" for group in groups)
