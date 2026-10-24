"""The meal-reminder consumer, end to end against both backends (NTF-202/NTF-203/NTF-602).

These run through the real recorder and the real stores, so what they assert is what a user
would actually find in their feed. The groups that matter are the acceptance criteria of the
story they sit under: the fixture events the meal scheduler publishes map onto the notification
intents the client renders (deep links included), and the arrivals that must not be acted on are
the ones that are replayed or malformed (NTF-103 / NTF-201).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.meal_reminder_consumer import (
    MEAL_REMINDER_CANCELLED,
    MEAL_REMINDER_DUE,
    MEAL_REMINDER_SCHEDULED,
)
from app.domain.deep_links import meal_deep_link
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.preferences import NotificationPreferences
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent
from tests.conftest import MealReminderConsumerHarness

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")


def meal_event(
    *,
    type: str = MEAL_REMINDER_DUE,
    user_id: uuid.UUID | str = USER,
    meal_id: str | None = None,
    meal_type: str = "breakfast",
    meal_name: str | None = None,
    scheduled_time: datetime | None = None,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    data: dict[str, Any] | None = None,
) -> EventEnvelope:
    """One meal-reminder event, shaped exactly as the scheduler publishes it."""
    if data is None:
        data = {
            "userId": str(user_id),
            "mealId": meal_id or str(uuid.uuid4()),
            "mealType": meal_type,
        }
        if meal_name is not None:
            data["mealName"] = meal_name
        data["scheduledTime"] = (scheduled_time or datetime.now(UTC)).isoformat()
    return EventEnvelope(
        schema_version=1,
        event_id=event_id or str(uuid.uuid4()),
        type=type,
        occurred_at=occurred_at or datetime.now(UTC),
        data=data,
    )


def muted(notification_type: NotificationType) -> NotificationPreferences:
    """`USER`'s preferences with one notification type switched off on every channel."""
    preferences = NotificationPreferences.defaults(USER)
    for channel in NotificationChannel:
        preferences = preferences.muting(notification_type, channel)
    return preferences


class TestMealReminderDue:
    def test_it_lands_in_the_users_feed(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        meal_reminder_consumer.consumer.handle(meal_event())

        assert meal_reminder_consumer.types(USER) == [NotificationType.MEAL_REMINDER.value]

    def test_the_payload_names_the_meal(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        meal_id = str(uuid.uuid4())
        moment = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
        meal_reminder_consumer.consumer.handle(
            meal_event(meal_id=meal_id, scheduled_time=moment, occurred_at=moment)
        )

        notification = meal_reminder_consumer.feed(USER)[0]
        assert notification.payload["mealId"] == meal_id
        assert notification.payload["mealName"] == "Breakfast"
        assert notification.payload["mealType"] == "breakfast"
        assert notification.payload["scheduledTime"] == moment.isoformat()
        assert notification.payload["deepLink"] == meal_deep_link(meal_id)
        assert notification.payload["occurredAt"] == moment.isoformat()

    def test_it_carries_a_deep_link_the_client_can_route(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """The deep link is the one the mobile router parses; the payload carries it verbatim."""
        meal_id = str(uuid.uuid4())
        meal_reminder_consumer.consumer.handle(
            meal_event(meal_id=meal_id, scheduled_time=datetime.now(UTC))
        )

        assert meal_reminder_consumer.feed(USER)[0].payload["deepLink"] == meal_deep_link(meal_id)

    def test_it_targets_both_surfaces(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """A due meal is worth a push; NTF-104's gate is what narrows that per user."""
        meal_reminder_consumer.consumer.handle(meal_event())

        assert set(meal_reminder_consumer.feed(USER)[0].channels) == {
            NotificationChannel.IN_APP,
            NotificationChannel.PUSH,
        }

    def test_it_is_addressed_to_the_user_on_the_event(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        someone_else = uuid.uuid4()

        meal_reminder_consumer.consumer.handle(meal_event(user_id=someone_else))

        assert meal_reminder_consumer.feed(someone_else) != []
        assert meal_reminder_consumer.feed(USER) == []


class TestMealReminderReplay:
    def test_a_replayed_event_records_nothing_new(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """NTF-103's guarantee, reached through the consumer that will rely on it."""
        delivery = meal_event()

        meal_reminder_consumer.consumer.handle(delivery)
        meal_reminder_consumer.consumer.handle(delivery)

        assert len(meal_reminder_consumer.feed(USER)) == 1


class TestMealReminderOptOut:
    def test_a_muted_type_records_nothing(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """NTF-104, reached through the consumer that finally exercises it."""
        meal_reminder_consumer.preferences.save(muted(NotificationType.MEAL_REMINDER))

        meal_reminder_consumer.consumer.handle(meal_event())

        assert meal_reminder_consumer.feed(USER) == []


class TestMealReminderNotNewsworthy:
    def test_scheduled_meal_reminder_records_nothing(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """Scheduling is bookkeeping, not news to the user; only the due moment is."""
        meal_reminder_consumer.consumer.handle(meal_event(type=MEAL_REMINDER_SCHEDULED))

        assert meal_reminder_consumer.feed(USER) == []

    def test_cancelled_meal_reminder_records_nothing(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """Cancelling before the meal is due means the user was never nudged."""
        meal_reminder_consumer.consumer.handle(meal_event(type=MEAL_REMINDER_CANCELLED))

        assert meal_reminder_consumer.feed(USER) == []


class TestMealReminderMalformedEvents:
    def test_a_missing_meal_id_is_permanently_malformed(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="mealId"):
            meal_reminder_consumer.consumer.handle(
                meal_event(
                    data={
                        "userId": str(USER),
                        "mealType": "breakfast",
                        "scheduledTime": datetime.now(UTC).isoformat(),
                    }
                )
            )

    def test_a_blank_meal_id_is_rejected(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """It would otherwise become a shared key every meal collided on."""
        with pytest.raises(MalformedEvent, match="mealId"):
            meal_reminder_consumer.consumer.handle(
                meal_event(
                    data={
                        "userId": str(USER),
                        "mealId": "  ",
                        "mealType": "breakfast",
                        "scheduledTime": datetime.now(UTC).isoformat(),
                    }
                )
            )

    def test_an_invalid_scheduled_time_is_permanently_malformed(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="scheduledTime"):
            meal_reminder_consumer.consumer.handle(
                meal_event(
                    data={
                        "userId": str(USER),
                        "mealId": "meal-1",
                        "mealType": "breakfast",
                        "scheduledTime": "not-a-date",
                    }
                )
            )

    def test_a_missing_user_is_permanently_malformed(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="userId"):
            meal_reminder_consumer.consumer.handle(
                meal_event(
                    data={
                        "mealId": "meal-1",
                        "mealType": "breakfast",
                        "scheduledTime": datetime.now(UTC).isoformat(),
                    }
                )
            )

    def test_an_unparseable_user_is_not_retried(
        self, meal_reminder_consumer: MealReminderConsumerHarness
    ) -> None:
        """Five retries would only delay the same conclusion."""
        with pytest.raises(MalformedEvent, match="userId"):
            meal_reminder_consumer.consumer.handle(meal_event(user_id="not-a-uuid"))
