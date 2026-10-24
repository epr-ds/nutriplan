"""The plan-ending consumer, end to end against both backends (NTF-202/NTF-402/NTF-602).

These run through the real recorder and the real stores, so what they assert is what a user
would actually find in their feed. The groups that matter are the acceptance criteria of the
story they sit under: the fixture events the plan scheduler publishes map onto the notification
intents the client renders (deep links included), and the arrivals that must not be acted on are
the ones that are replayed or malformed (NTF-103 / NTF-201).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.plan_ending_consumer import (
    PLAN_ENDED,
    PLAN_ENDING_SOON,
    PLAN_RENEWAL_DUE,
)
from app.domain.deep_links import plan_deep_link
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.preferences import NotificationPreferences
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent
from tests.conftest import PlanEndingConsumerHarness

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")


def plan_event(
    *,
    type: str = PLAN_ENDING_SOON,
    user_id: uuid.UUID | str = USER,
    plan_id: str | None = None,
    plan_type: str = "weekly",
    ending_date: datetime | None = None,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    data: dict[str, Any] | None = None,
) -> EventEnvelope:
    """One plan-ending event, shaped exactly as the scheduler publishes it."""
    if data is None:
        data = {
            "userId": str(user_id),
            "planId": plan_id or str(uuid.uuid4()),
            "planType": plan_type,
            "endingDate": (ending_date or datetime.now(UTC)).isoformat(),
        }
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


class TestPlanEndingSoon:
    def test_it_lands_in_the_users_feed(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        plan_ending_consumer.consumer.handle(plan_event())

        assert plan_ending_consumer.types(USER) == [NotificationType.PLAN_ENDING.value]

    def test_the_payload_names_the_plan(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        plan_id = str(uuid.uuid4())
        ending_date = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        plan_ending_consumer.consumer.handle(
            plan_event(plan_id=plan_id, ending_date=ending_date, occurred_at=ending_date)
        )

        notification = plan_ending_consumer.feed(USER)[0]
        assert notification.payload["planId"] == plan_id
        assert notification.payload["planType"] == "weekly"
        assert notification.payload["endingDate"] == ending_date.isoformat()
        assert notification.payload["deepLink"] == plan_deep_link(plan_id, "manage")
        assert notification.payload["occurredAt"] == ending_date.isoformat()

    def test_it_carries_a_deep_link_to_the_manage_screen(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        """The deep link is the one the mobile router parses; the payload carries it verbatim."""
        plan_id = str(uuid.uuid4())
        plan_ending_consumer.consumer.handle(
            plan_event(plan_id=plan_id, ending_date=datetime.now(UTC))
        )

        assert plan_ending_consumer.feed(USER)[0].payload["deepLink"] == plan_deep_link(
            plan_id, "manage"
        )

    def test_it_targets_both_surfaces(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        """A plan ending is worth a push; NTF-104's gate is what narrows that per user."""
        plan_ending_consumer.consumer.handle(plan_event())

        assert set(plan_ending_consumer.feed(USER)[0].channels) == {
            NotificationChannel.IN_APP,
            NotificationChannel.PUSH,
        }

    def test_it_is_addressed_to_the_user_on_the_event(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        someone_else = uuid.uuid4()

        plan_ending_consumer.consumer.handle(plan_event(user_id=someone_else))

        assert plan_ending_consumer.feed(someone_else) != []
        assert plan_ending_consumer.feed(USER) == []


class TestPlanEndingReplay:
    def test_a_replayed_event_records_nothing_new(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        """NTF-103's guarantee, reached through the consumer that will rely on it."""
        delivery = plan_event()

        plan_ending_consumer.consumer.handle(delivery)
        plan_ending_consumer.consumer.handle(delivery)

        assert len(plan_ending_consumer.feed(USER)) == 1


class TestPlanEndingOptOut:
    def test_a_muted_type_records_nothing(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        """NTF-104, reached through the consumer that finally exercises it."""
        plan_ending_consumer.preferences.save(muted(NotificationType.PLAN_ENDING))

        plan_ending_consumer.consumer.handle(plan_event())

        assert plan_ending_consumer.feed(USER) == []


class TestPlanEndingCompletedAndRenewal:
    def test_a_completed_plan_ending_links_to_the_summary(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        plan_id = str(uuid.uuid4())
        ending_date = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        plan_ending_consumer.consumer.handle(
            plan_event(type=PLAN_ENDED, plan_id=plan_id, ending_date=ending_date)
        )

        notification = plan_ending_consumer.feed(USER)[0]
        assert notification.type == NotificationType.PLAN_ENDED
        assert notification.payload["planId"] == plan_id
        assert notification.payload["endedDate"] == ending_date.isoformat()
        assert notification.payload["deepLink"] == plan_deep_link(plan_id, "summary")

    def test_a_due_plan_renewal_links_to_the_renew_screen(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        plan_id = str(uuid.uuid4())
        ending_date = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        plan_ending_consumer.consumer.handle(
            plan_event(type=PLAN_RENEWAL_DUE, plan_id=plan_id, ending_date=ending_date)
        )

        notification = plan_ending_consumer.feed(USER)[0]
        assert notification.type == NotificationType.PLAN_RENEWAL
        assert notification.payload["planId"] == plan_id
        assert notification.payload["renewalDate"] == ending_date.isoformat()
        assert notification.payload["deepLink"] == plan_deep_link(plan_id, "renew")


class TestPlanEndingMalformedEvents:
    def test_a_missing_plan_id_is_permanently_malformed(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="planId"):
            plan_ending_consumer.consumer.handle(
                plan_event(
                    data={
                        "userId": str(USER),
                        "planType": "weekly",
                        "endingDate": "2026-03-01T12:00:00",
                    }
                )
            )

    def test_a_missing_plan_type_is_permanently_malformed(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="planType"):
            plan_ending_consumer.consumer.handle(
                plan_event(
                    data={
                        "userId": str(USER),
                        "planId": "plan-1",
                        "endingDate": "2026-03-01T12:00:00",
                    }
                )
            )

    def test_an_invalid_ending_date_is_permanently_malformed(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="endingDate"):
            plan_ending_consumer.consumer.handle(
                plan_event(
                    data={
                        "userId": str(USER),
                        "planId": "plan-1",
                        "planType": "weekly",
                        "endingDate": "not-a-date",
                    }
                )
            )

    def test_a_missing_user_is_permanently_malformed(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        with pytest.raises(MalformedEvent, match="userId"):
            plan_ending_consumer.consumer.handle(
                plan_event(
                    data={
                        "planId": "plan-1",
                        "planType": "weekly",
                        "endingDate": "2026-03-01T12:00:00",
                    }
                )
            )


class TestPlanEndingUnhandled:
    def test_an_unknown_event_type_is_a_handled_noop(
        self, plan_ending_consumer: PlanEndingConsumerHarness
    ) -> None:
        """Not our traffic: the consumer acks it instead of parking it for replay."""
        plan_ending_consumer.consumer.handle(plan_event(type="plan.ending.never-heard-of"))

        assert plan_ending_consumer.feed(USER) == []
