"""Which consumer the service builds, and from what (NTF-201, AC3).

The choice these tests pin is the one that decides whether events survive a restart: an
in-process consumer is right for a laptop and catastrophic in production, and the only thing
standing between the two is a config value. So the selection is asserted directly rather than
inferred from a service that happens to work.
"""

from __future__ import annotations

from app.core.config import Settings
from app.events.dispatcher import EventDispatcher
from app.events.factory import (
    build_dead_letter_sink,
    build_event_consumer,
    build_event_dispatcher,
)
from app.events.memory import InMemoryEventConsumer
from app.events.redis_stream import RedisStreamEventConsumer
from app.events.registry import (
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_EVENT_VERSION,
    ORDER_STATUS_CHANGED,
)


class TestChoosingTheBackend:
    def test_no_configured_bus_gives_the_in_process_consumer(self) -> None:
        """Dev and CI need a working consumer without a broker; NTF-101 warns about it."""
        assert isinstance(build_event_consumer(Settings()), InMemoryEventConsumer)

    def test_a_configured_bus_gives_the_redis_consumer(self) -> None:
        consumer = build_event_consumer(Settings(event_bus_url="redis://unreachable:6379/0"))

        assert isinstance(consumer, RedisStreamEventConsumer)

    def test_it_falls_back_to_the_notification_redis(self) -> None:
        """One Redis until there is a reason for two -- NTF-101's ``effective_event_bus_url``."""
        consumer = build_event_consumer(Settings(redis_url="redis://unreachable:6379/0"))

        assert isinstance(consumer, RedisStreamEventConsumer)

    def test_building_a_redis_consumer_opens_no_connection(self) -> None:
        """Construction must not fail because the broker is down; ``ensure_group`` may."""
        build_event_consumer(Settings(event_bus_url="redis://nowhere.invalid:6379/0"))

    def test_it_consumes_the_stream_commerce_publishes_to(self) -> None:
        """The one string that has to match COM-109 exactly, or nothing is ever delivered."""
        consumer = build_event_consumer(Settings(event_bus_url="redis://unreachable:6379/0"))

        assert consumer.stream == "commerce.order-events"  # type: ignore[union-attr]

    def test_it_uses_the_configured_group_and_consumer_names(self) -> None:
        consumer = build_event_consumer(
            Settings(
                event_bus_url="redis://unreachable:6379/0",
                consumer_group="notifications-blue",
                consumer_name="pod-7",
            )
        )

        assert consumer.group == "notifications-blue"  # type: ignore[union-attr]


class TestTheAssembledDispatcher:
    def test_it_is_built_without_touching_a_broker(self) -> None:
        """Wiring must be safe at import/DI time; connecting is ``ensure_subscribed``'s job."""
        dispatcher = build_event_dispatcher(Settings(event_bus_url="redis://nowhere.invalid:6379"))

        assert isinstance(dispatcher, EventDispatcher)

    def test_it_ships_with_the_order_consumer_registered(self) -> None:
        """NTF-201 built the framework; NTF-202 is the first behaviour plugged into it."""
        assert build_event_dispatcher(Settings()).handled_types == (
            ORDER_CONFIRMED,
            ORDER_STATUS_CHANGED,
        )

    def test_order_created_is_deliberately_left_unhandled(self) -> None:
        """The user is watching the confirmation screen as it arrives, so it is not news.

        Visible here rather than as an early ``return`` inside the handler: the absence of a
        registration *is* the decision, and NTF-201 acks an event with no handler.
        """
        assert ORDER_CREATED not in build_event_dispatcher(Settings()).handled_types

    def test_a_handler_set_can_be_substituted(self) -> None:
        """So a test can drive the dispatcher without the production consumer attached."""
        assert build_event_dispatcher(Settings(), handlers={}).handled_types == ()

    def test_a_collaborator_can_be_substituted(self) -> None:
        """The seam NTF-202's tests will use to drive the dispatcher off a fake consumer."""
        consumer = InMemoryEventConsumer()

        dispatcher = build_event_dispatcher(Settings(), consumer=consumer)

        assert dispatcher.poll_once(count=1, block_ms=0).total == 0

    def test_a_dead_letter_sink_is_always_present(self) -> None:
        """So "park it" is a real branch from day one rather than a silent drop."""
        assert build_dead_letter_sink(Settings()).parked == ()  # type: ignore[attr-defined]


class TestTheEventingConfiguration:
    def test_the_defaults_need_no_broker(self) -> None:
        settings = Settings()

        assert settings.event_bus_url == ""
        assert settings.event_bus_configured is False

    def test_the_reclaim_idle_window_outlasts_a_slow_handler(self) -> None:
        """Reclaiming a healthy in-flight message manufactures a duplicate delivery."""
        settings = Settings()

        assert settings.event_reclaim_idle_ms > settings.event_block_ms

    def test_the_retry_budget_is_finite(self) -> None:
        """An infinite budget turns one poison message into a permanent redelivery loop."""
        assert Settings().event_max_delivery_attempts >= 1

    def test_the_order_schemas_are_registered_at_the_version_commerce_publishes(self) -> None:
        assert ORDER_EVENT_VERSION == 1
        assert ORDER_CREATED == "order.created"
