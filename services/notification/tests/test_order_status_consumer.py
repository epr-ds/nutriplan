"""The order-status consumer, end to end against both backends (NTF-202).

These run through the real recorder and the real stores, so what they assert is what a user
would actually find in their feed. The three groups that matter are the acceptance criteria:
the mapping (AC1), the notification intents that come out of it (AC2), and the two ways an
event can arrive that it should not be acted on -- replayed, or overtaken (AC3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.enums import NotificationChannel, NotificationType
from app.domain.order_status import OrderStatus
from app.domain.preferences import NotificationPreferences
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent, UnsupportedEvent
from app.events.registry import ORDER_CONFIRMED, ORDER_EVENT_VERSION, ORDER_STATUS_CHANGED
from tests.conftest import OrderConsumerHarness

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")


def event(
    *,
    type: str = ORDER_STATUS_CHANGED,
    order_id: str | None = None,
    user_id: uuid.UUID | str = USER,
    to_status: str | None = "preparing",
    from_status: str | None = "confirmed",
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    data: dict[str, Any] | None = None,
) -> EventEnvelope:
    """One commerce order event, shaped exactly as COM-109 publishes it."""
    if data is None:
        data = {
            "orderId": order_id or str(uuid.uuid4()),
            "userId": str(user_id),
        }
        if to_status is not None:
            data["toStatus"] = to_status
        if from_status is not None:
            data["fromStatus"] = from_status
    return EventEnvelope(
        schema_version=ORDER_EVENT_VERSION,
        event_id=event_id or str(uuid.uuid4()),
        type=type,
        occurred_at=occurred_at or datetime.now(UTC),
        data=data,
    )


def mute(notification_type: NotificationType) -> NotificationPreferences:
    """`USER`'s preferences with one notification type switched off on every channel."""
    preferences = NotificationPreferences.defaults(USER)
    for channel in NotificationChannel:
        preferences = preferences.muting(notification_type, channel)
    return preferences


def confirmed(**overrides: Any) -> EventEnvelope:
    """The dedicated ``pending -> confirmed`` event commerce publishes for that one move."""
    overrides.setdefault("type", ORDER_CONFIRMED)
    overrides.setdefault("to_status", "confirmed")
    overrides.setdefault("from_status", "pending")
    return event(**overrides)


class TestRecordingAStatusChange:
    def test_it_lands_in_the_users_feed(self, order_consumer: OrderConsumerHarness) -> None:
        order_consumer.consumer.handle(event(to_status="in_transit"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_IN_TRANSIT.value]

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("preparing", NotificationType.ORDER_PREPARING),
            ("in_transit", NotificationType.ORDER_IN_TRANSIT),
            ("delivered", NotificationType.ORDER_DELIVERED),
            ("cancelled", NotificationType.ORDER_CANCELLED),
        ],
    )
    def test_each_status_becomes_its_own_intent(
        self, order_consumer: OrderConsumerHarness, status: str, expected: NotificationType
    ) -> None:
        order_consumer.consumer.handle(event(to_status=status))

        assert order_consumer.types(USER) == [expected.value]

    def test_the_dedicated_confirmed_event_is_handled_too(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Commerce routes ``pending -> confirmed`` to its own type; both paths must work."""
        order_consumer.consumer.handle(confirmed())

        assert order_consumer.types(USER) == [NotificationType.ORDER_CONFIRMED.value]

    def test_the_event_type_wins_over_the_payload_for_confirmed(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """The type is what commerce routed on, so it is the more trustworthy of the two."""
        order_consumer.consumer.handle(confirmed(to_status="preparing"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_CONFIRMED.value]

    def test_it_is_addressed_to_the_user_on_the_event(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        someone_else = uuid.uuid4()

        order_consumer.consumer.handle(event(user_id=someone_else))

        assert order_consumer.feed(someone_else) != []
        assert order_consumer.feed(USER) == []

    def test_it_targets_both_surfaces(self, order_consumer: OrderConsumerHarness) -> None:
        """An order update is worth a push; NTF-104's gate is what narrows that per user."""
        order_consumer.consumer.handle(event())

        assert set(order_consumer.feed(USER)[0].channels) == {
            NotificationChannel.IN_APP,
            NotificationChannel.PUSH,
        }


class TestWhatTheClientGetsToRender:
    def test_the_payload_names_the_order(self, order_consumer: OrderConsumerHarness) -> None:
        order_id = str(uuid.uuid4())

        order_consumer.consumer.handle(event(order_id=order_id))

        assert order_consumer.feed(USER)[0].payload["orderId"] == order_id

    def test_it_carries_commerce_status_vocabulary_verbatim(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """The client already speaks it from the orders API; a second dialect would drift."""
        order_consumer.consumer.handle(event(to_status="in_transit", from_status="preparing"))

        payload = order_consumer.feed(USER)[0].payload
        assert payload["status"] == "in_transit"
        assert payload["previousStatus"] == "preparing"

    def test_it_carries_when_the_order_actually_moved(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """So the copy can say "delivered at 3:04" rather than when we happened to store it."""
        moment = datetime(2026, 3, 1, 15, 4, tzinfo=UTC)

        order_consumer.consumer.handle(event(occurred_at=moment))

        assert order_consumer.feed(USER)[0].payload["occurredAt"] == moment.isoformat()

    def test_a_missing_previous_status_is_not_fatal(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """It is context for rendering, not a decision input."""
        order_consumer.consumer.handle(event(from_status=None))

        assert "previousStatus" not in order_consumer.feed(USER)[0].payload

    def test_a_replayed_event_surfaces_at_the_top_of_the_feed(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Back-dating it to ``occurredAt`` would file it under a day already scrolled past."""
        long_ago = datetime.now(UTC) - timedelta(days=30)

        order_consumer.consumer.handle(event(occurred_at=long_ago))

        assert order_consumer.feed(USER)[0].created_at > long_ago + timedelta(days=29)


class TestStatusesThatAreNotNews:
    def test_pending_records_nothing(self, order_consumer: OrderConsumerHarness) -> None:
        """The user is looking at the confirmation screen as it arrives."""
        order_consumer.consumer.handle(event(to_status="pending"))

        assert order_consumer.feed(USER) == []

    def test_pending_is_acked_not_raised(self, order_consumer: OrderConsumerHarness) -> None:
        """A deliberate no-op is a handled event; raising would have NTF-201 retry it."""
        order_consumer.consumer.handle(event(to_status="pending"))

    def test_pending_does_not_block_the_real_first_notification(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Its rank must not become a mark that suppresses ``confirmed`` behind it."""
        order_id = str(uuid.uuid4())
        order_consumer.consumer.handle(event(order_id=order_id, to_status="pending"))

        order_consumer.consumer.handle(confirmed(order_id=order_id))

        assert order_consumer.types(USER) == [NotificationType.ORDER_CONFIRMED.value]


class TestAStatusThisBuildDoesNotKnow:
    def test_it_is_permanent_rather_than_retried(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """``UnsupportedEvent`` parks it for NTF-204 replay once the mapping ships."""
        with pytest.raises(UnsupportedEvent):
            order_consumer.consumer.handle(event(to_status="refunded"))

    def test_the_reason_names_the_status(self, order_consumer: OrderConsumerHarness) -> None:
        with pytest.raises(UnsupportedEvent, match="refunded"):
            order_consumer.consumer.handle(event(to_status="refunded"))

    def test_nothing_is_recorded_for_it(self, order_consumer: OrderConsumerHarness) -> None:
        with pytest.raises(UnsupportedEvent):
            order_consumer.consumer.handle(event(to_status="refunded"))

        assert order_consumer.feed(USER) == []

    def test_it_does_not_move_the_mark(self, order_consumer: OrderConsumerHarness) -> None:
        """A parked event replayed later must still be able to notify."""
        order_id = str(uuid.uuid4())
        with pytest.raises(UnsupportedEvent):
            order_consumer.consumer.handle(event(order_id=order_id, to_status="refunded"))

        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_DELIVERED.value]


class TestEventsThatCannotBeRead:
    def test_a_missing_status_is_permanently_malformed(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="toStatus"):
            order_consumer.consumer.handle(event(to_status=None))

    def test_a_missing_order_id_is_permanently_malformed(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="orderId"):
            order_consumer.consumer.handle(
                event(data={"userId": str(USER), "toStatus": "delivered"})
            )

    def test_a_blank_order_id_is_rejected(self, order_consumer: OrderConsumerHarness) -> None:
        """It would otherwise become a shared key every order collided on."""
        with pytest.raises(MalformedEvent, match="orderId"):
            order_consumer.consumer.handle(
                event(data={"orderId": "  ", "userId": str(USER), "toStatus": "delivered"})
            )

    def test_a_missing_user_is_permanently_malformed(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="userId"):
            order_consumer.consumer.handle(
                event(data={"orderId": str(uuid.uuid4()), "toStatus": "delivered"})
            )

    def test_an_unparseable_user_is_not_retried(self, order_consumer: OrderConsumerHarness) -> None:
        """Five retries would only delay the same conclusion."""
        with pytest.raises(MalformedEvent, match="userId"):
            order_consumer.consumer.handle(event(user_id="not-a-uuid"))


class TestAReplayedEvent:
    def test_the_second_delivery_records_nothing(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """NTF-103's guarantee, now reached through the consumer that will rely on it."""
        delivery = event(to_status="delivered")

        order_consumer.consumer.handle(delivery)
        order_consumer.consumer.handle(delivery)

        assert order_consumer.types(USER) == [NotificationType.ORDER_DELIVERED.value]

    def test_it_is_the_producer_event_id_that_identifies_a_replay(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """NTF-204 re-adds a parked event: new broker id, same envelope id, one notification."""
        order_id = str(uuid.uuid4())
        original = event(order_id=order_id, to_status="delivered", event_id="evt-1")
        replay = event(order_id=order_id, to_status="delivered", event_id="evt-1")

        order_consumer.consumer.handle(original)
        order_consumer.consumer.handle(replay)

        assert len(order_consumer.feed(USER)) == 1

    def test_replaying_a_whole_order_history_adds_nothing(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        order_id = str(uuid.uuid4())
        history = [
            confirmed(order_id=order_id),
            event(order_id=order_id, to_status="preparing"),
            event(order_id=order_id, to_status="in_transit"),
            event(order_id=order_id, to_status="delivered"),
        ]
        for delivery in history:
            order_consumer.consumer.handle(delivery)

        for delivery in history:
            order_consumer.consumer.handle(delivery)

        assert len(order_consumer.feed(USER)) == 4


class TestAnEventThatArrivesTooLate:
    def test_a_stale_status_is_not_announced(self, order_consumer: OrderConsumerHarness) -> None:
        """The headline case: "on its way" must never follow "delivered"."""
        order_id = str(uuid.uuid4())
        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        order_consumer.consumer.handle(event(order_id=order_id, to_status="in_transit"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_DELIVERED.value]

    def test_it_is_a_different_event_than_a_replay(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Distinct event ids, so dedupe has nothing to say -- only the mark can catch it."""
        order_id = str(uuid.uuid4())
        order_consumer.consumer.handle(
            event(order_id=order_id, to_status="delivered", event_id="evt-late")
        )

        order_consumer.consumer.handle(
            event(order_id=order_id, to_status="preparing", event_id="evt-early")
        )

        assert len(order_consumer.feed(USER)) == 1

    def test_a_stale_event_is_acked_not_raised(self, order_consumer: OrderConsumerHarness) -> None:
        """Retrying it would produce the same answer five times and then park it."""
        order_id = str(uuid.uuid4())
        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        order_consumer.consumer.handle(event(order_id=order_id, to_status="preparing"))

    def test_nothing_survives_a_cancellation(self, order_consumer: OrderConsumerHarness) -> None:
        """Telling someone their cancelled order is being prepared is the worst outcome."""
        order_id = str(uuid.uuid4())
        order_consumer.consumer.handle(event(order_id=order_id, to_status="cancelled"))

        order_consumer.consumer.handle(event(order_id=order_id, to_status="preparing"))
        order_consumer.consumer.handle(event(order_id=order_id, to_status="in_transit"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_CANCELLED.value]

    def test_out_of_order_arrival_keeps_the_furthest_status(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        order_id = str(uuid.uuid4())
        for status in ("delivered", "preparing", "in_transit", "confirmed"):
            order_consumer.consumer.handle(event(order_id=order_id, to_status=status))

        assert order_consumer.types(USER) == [NotificationType.ORDER_DELIVERED.value]

    def test_other_orders_are_unaffected(self, order_consumer: OrderConsumerHarness) -> None:
        """The mark is per order; one delivered order must not mute another's progress."""
        delivered_order, fresh_order = str(uuid.uuid4()), str(uuid.uuid4())
        order_consumer.consumer.handle(event(order_id=delivered_order, to_status="delivered"))

        order_consumer.consumer.handle(event(order_id=fresh_order, to_status="preparing"))

        assert NotificationType.ORDER_PREPARING.value in order_consumer.types(USER)


class TestTheHappyPath:
    def test_every_step_notifies_once(self, order_consumer: OrderConsumerHarness) -> None:
        order_id = str(uuid.uuid4())

        order_consumer.consumer.handle(confirmed(order_id=order_id))
        for status in ("preparing", "in_transit", "delivered"):
            order_consumer.consumer.handle(event(order_id=order_id, to_status=status))

        assert set(order_consumer.types(USER)) == {
            NotificationType.ORDER_CONFIRMED.value,
            NotificationType.ORDER_PREPARING.value,
            NotificationType.ORDER_IN_TRANSIT.value,
            NotificationType.ORDER_DELIVERED.value,
        }

    def test_the_mark_ends_where_the_order_did(self, order_consumer: OrderConsumerHarness) -> None:
        from app.domain.order_status import progress_of

        order_id = str(uuid.uuid4())
        for status in ("preparing", "delivered"):
            order_consumer.consumer.handle(event(order_id=order_id, to_status=status))

        assert order_consumer.progress.progress_of(order_id) == progress_of(OrderStatus.DELIVERED)

    def test_a_skipped_step_does_not_block_what_follows(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Commerce need not publish every intermediate transition."""
        order_id = str(uuid.uuid4())

        order_consumer.consumer.handle(confirmed(order_id=order_id))
        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        assert len(order_consumer.feed(USER)) == 2


class TestThePreferenceGate:
    def test_a_muted_type_records_nothing(self, order_consumer: OrderConsumerHarness) -> None:
        """NTF-104, reached through the consumer that finally exercises it."""
        order_consumer.preferences.save(mute(NotificationType.ORDER_PREPARING))

        order_consumer.consumer.handle(event(to_status="preparing"))

        assert order_consumer.feed(USER) == []

    def test_suppression_still_advances_the_mark(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        """Otherwise un-muting would let a stale earlier status through afterwards."""
        order_id = str(uuid.uuid4())
        order_consumer.preferences.save(mute(NotificationType.ORDER_DELIVERED))
        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        order_consumer.consumer.handle(event(order_id=order_id, to_status="in_transit"))

        assert order_consumer.feed(USER) == []

    def test_a_muted_type_does_not_mute_the_others(
        self, order_consumer: OrderConsumerHarness
    ) -> None:
        order_consumer.preferences.save(mute(NotificationType.ORDER_PREPARING))
        order_id = str(uuid.uuid4())

        order_consumer.consumer.handle(event(order_id=order_id, to_status="preparing"))
        order_consumer.consumer.handle(event(order_id=order_id, to_status="delivered"))

        assert order_consumer.types(USER) == [NotificationType.ORDER_DELIVERED.value]
