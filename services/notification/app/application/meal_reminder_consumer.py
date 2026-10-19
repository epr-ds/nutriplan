"""Meal reminder notification consumer (NTF-401).

This module provides the consumer that turns scheduled meal reminders into
in-app notifications and push notifications.

Meal reminders are triggered by:
- User-defined meal times (breakfast, lunch, dinner, snacks)
- Dietary plan schedules
- User preferences for reminder timing

The consumer handles:
- Parsing meal reminder events
- Checking user preferences for reminder channels
- Building notification payloads with deep links to meal details
- Sending via FCM/APNs adapters
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.push_delivery import PushDelivery
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent

logger = logging.getLogger(__name__)

# Event types handled by this consumer
MEAL_REMINDER_SCHEDULED = "meal.reminder.scheduled"
MEAL_REMINDER_DUE = "meal.reminder.due"
MEAL_REMINDER_CANCELLED = "meal.reminder.cancelled"

HANDLED_EVENT_TYPES: tuple[str, ...] = (
    MEAL_REMINDER_SCHEDULED,
    MEAL_REMINDER_DUE,
    MEAL_REMINDER_CANCELLED,
)

DEFAULT_CHANNELS: tuple[NotificationChannel, ...] = (
    NotificationChannel.PUSH,
    NotificationChannel.IN_APP,
)


@dataclass(frozen=True)
class MealReminderPayload:
    """Structured meal reminder data."""

    meal_id: str
    user_id: uuid.UUID
    meal_type: str  # breakfast, lunch, dinner, snack
    meal_name: str
    scheduled_time: datetime
    deep_link: str
    notification_type: NotificationType = NotificationType.MEAL_REMINDER


class MealReminderConsumer:
    """Processes meal reminder events and creates notifications."""

    def __init__(
        self,
        recorder: Any,  # NotificationRecorder
        *,
        channels: tuple[NotificationChannel, ...] = DEFAULT_CHANNELS,
        push: PushDelivery | None = None,
    ) -> None:
        self._recorder = recorder
        self._channels = channels
        self._push = push

    def handle(self, envelope: EventEnvelope) -> None:
        """Handle a meal reminder event.

        For MEAL_REMINDER_DUE events, creates a notification.
        For MEAL_REMINDER_SCHEDULED events, logs the schedule.
        For MEAL_REMINDER_CANCELLED events, logs the cancellation.
        """
        if envelope.type == MEAL_REMINDER_DUE:
            self._handle_due(envelope)
        elif envelope.type == MEAL_REMINDER_SCHEDULED:
            self._handle_scheduled(envelope)
        elif envelope.type == MEAL_REMINDER_CANCELLED:
            self._handle_cancelled(envelope)
        else:
            logger.warning(
                "meal_reminder.unhandled_type event_id=%s type=%s",
                envelope.event_id,
                envelope.type,
            )

    def _handle_due(self, envelope: EventEnvelope) -> None:
        """Create a notification for a due meal reminder."""
        user_id = self._parse_user_id(envelope)
        meal_data = self._parse_meal_data(envelope)

        # Build deep link to meal details
        deep_link = f"nutriplan://meal/{meal_data.meal_id}"

        # Build notification
        notification = Notification(
            user_id=user_id,
            type=meal_data.notification_type,
            payload={
                "mealId": meal_data.meal_id,
                "mealName": meal_data.meal_name,
                "mealType": meal_data.meal_type,
                "scheduledTime": meal_data.scheduled_time.isoformat(),
                "deepLink": deep_link,
                "occurredAt": envelope.occurred_at.isoformat(),
            },
            channels=self._channels,
        )

        result = self._recorder.record(notification, event_id=envelope.event_id)
        if result.recorded:
            logger.info(
                "meal_reminder.due notification_recorded meal_id=%s user_id=%s",
                meal_data.meal_id,
                user_id,
            )
            if result.notification is not None and self._push is not None:
                self._push.deliver(result.notification)
        elif result.duplicate:
            logger.info(
                "meal_reminder.due duplicate meal_id=%s",
                meal_data.meal_id,
            )
        else:
            logger.info(
                "meal_reminder.due suppressed meal_id=%s channels=%s",
                meal_data.meal_id,
                ",".join(c.value for c in result.suppressed_channels),
            )

    def _handle_scheduled(self, envelope: EventEnvelope) -> None:
        """Log a scheduled meal reminder."""
        meal_data = self._parse_meal_data(envelope)
        logger.info(
            "meal_reminder.scheduled meal_id=%s type=%s time=%s",
            meal_data.meal_id,
            meal_data.meal_type,
            meal_data.scheduled_time.isoformat(),
        )

    def _handle_cancelled(self, envelope: EventEnvelope) -> None:
        """Log a cancelled meal reminder."""
        meal_id = self._require_string(envelope.data, "mealId")
        logger.info(
            "meal_reminder.cancelled meal_id=%s",
            meal_id,
        )

    def _parse_user_id(self, envelope: EventEnvelope) -> uuid.UUID:
        """Parse the user ID from the envelope."""
        raw = envelope.require("userId")
        try:
            return uuid.UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            raise MalformedEvent(
                f"event {envelope.event_id} ({envelope.type}) has an unusable userId {raw!r}"
            ) from None

    def _parse_meal_data(self, envelope: EventEnvelope) -> MealReminderPayload:
        """Parse meal reminder data from the envelope."""
        meal_id = self._require_string(envelope.data, "mealId")
        meal_type = self._require_string(envelope.data, "mealType")
        meal_name = envelope.data.get("mealName", meal_type.title())
        scheduled_time_str = self._require_string(envelope.data, "scheduledTime")

        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
        except (ValueError, TypeError):
            raise MalformedEvent(
                f"event {envelope.event_id} ({envelope.type}) has invalid "
                f"scheduledTime {scheduled_time_str!r}"
            ) from None

        return MealReminderPayload(
            meal_id=meal_id,
            user_id=self._parse_user_id(envelope),
            meal_type=meal_type,
            meal_name=meal_name,
            scheduled_time=scheduled_time,
            deep_link=f"nutriplan://meal/{meal_id}",
        )

    @staticmethod
    def _require_string(data: Mapping[str, Any], key: str) -> str:
        """Require a string field in the data."""
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MalformedEvent(f"missing or invalid field: {key}")
        return value.strip()

    @property
    def notification_types(self) -> tuple[NotificationType, ...]:
        """Every notification type this consumer can produce."""
        return (NotificationType.MEAL_REMINDER,)
