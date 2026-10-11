"""Plan ending notification consumer (NTF-402).

This module provides the consumer that handles plan ending events and creates
notifications to inform users about their upcoming or completed plan endings.

Plan ending events are triggered by:
- Plan expiration dates
- Plan renewal reminders
- Plan cancellation notifications

The consumer handles:
- Parsing plan ending events
- Checking user preferences for notification channels
- Building notification payloads with deep links to plan management
- Sending via FCM/APNs adapters
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent

logger = logging.getLogger(__name__)

# Event types handled by this consumer
PLAN_ENDING_SOON = "plan.ending.soon"
PLAN_ENDED = "plan.ended"
PLAN_RENEWAL_DUE = "plan.renewal.due"

HANDLED_EVENT_TYPES: tuple[str, ...] = (
    PLAN_ENDING_SOON,
    PLAN_ENDED,
    PLAN_RENEWAL_DUE,
)

DEFAULT_CHANNELS: tuple[NotificationChannel, ...] = (
    NotificationChannel.PUSH,
    NotificationChannel.IN_APP,
)


@dataclass(frozen=True)
class PlanEndingPayload:
    """Structured plan ending data."""

    plan_id: str
    user_id: uuid.UUID
    plan_type: str  # weekly, monthly, annual
    ending_date: datetime
    deep_link: str
    notification_type: NotificationType = NotificationType.PLAN_ENDING


class PlanEndingConsumer:
    """Processes plan ending events and creates notifications."""

    def __init__(
        self,
        recorder: Any,  # NotificationRecorder
        *,
        channels: tuple[NotificationChannel, ...] = DEFAULT_CHANNELS,
    ) -> None:
        self._recorder = recorder
        self._channels = channels

    def handle(self, envelope: EventEnvelope) -> None:
        """Handle a plan ending event.

        For PLAN_ENDING_SOON events, creates a reminder notification.
        For PLAN_ENDED events, creates a completion notification.
        For PLAN_RENEWAL_DUE events, creates a renewal reminder.
        """
        if envelope.type == PLAN_ENDING_SOON:
            self._handle_ending_soon(envelope)
        elif envelope.type == PLAN_ENDED:
            self._handle_ended(envelope)
        elif envelope.type == PLAN_RENEWAL_DUE:
            self._handle_renewal_due(envelope)
        else:
            logger.warning(
                "plan_ending.unhandled_type event_id=%s type=%s",
                envelope.event_id,
                envelope.type,
            )

    def _handle_ending_soon(self, envelope: EventEnvelope) -> None:
        """Create a notification for an upcoming plan ending."""
        user_id = self._parse_user_id(envelope)
        plan_data = self._parse_plan_data(envelope)

        # Build deep link to plan management
        deep_link = f"nutriplan://plan/{plan_data.plan_id}/manage"

        # Build notification
        notification = Notification(
            user_id=user_id,
            type=plan_data.notification_type,
            payload={
                "planId": plan_data.plan_id,
                "planType": plan_data.plan_type,
                "endingDate": plan_data.ending_date.isoformat(),
                "deepLink": deep_link,
                "occurredAt": envelope.occurred_at.isoformat(),
            },
            channels=self._channels,
        )

        result = self._recorder.record(notification, event_id=envelope.event_id)
        if result.recorded:
            logger.info(
                "plan_ending.soon notification_recorded plan_id=%s user_id=%s",
                plan_data.plan_id,
                user_id,
            )
        elif result.duplicate:
            logger.info(
                "plan_ending.soon duplicate plan_id=%s",
                plan_data.plan_id,
            )
        else:
            logger.info(
                "plan_ending.soon suppressed plan_id=%s channels=%s",
                plan_data.plan_id,
                ",".join(c.value for c in result.suppressed_channels),
            )

    def _handle_ended(self, envelope: EventEnvelope) -> None:
        """Create a notification for a completed plan ending."""
        user_id = self._parse_user_id(envelope)
        plan_data = self._parse_plan_data(envelope)

        # Build deep link to plan management
        deep_link = f"nutriplan://plan/{plan_data.plan_id}/summary"

        # Build notification
        notification = Notification(
            user_id=user_id,
            type=NotificationType.PLAN_ENDED,
            payload={
                "planId": plan_data.plan_id,
                "planType": plan_data.plan_type,
                "endedDate": plan_data.ending_date.isoformat(),
                "deepLink": deep_link,
                "occurredAt": envelope.occurred_at.isoformat(),
            },
            channels=self._channels,
        )

        result = self._recorder.record(notification, event_id=envelope.event_id)
        if result.recorded:
            logger.info(
                "plan_ending.ended notification_recorded plan_id=%s user_id=%s",
                plan_data.plan_id,
                user_id,
            )
        elif result.duplicate:
            logger.info(
                "plan_ending.ended duplicate plan_id=%s",
                plan_data.plan_id,
            )
        else:
            logger.info(
                "plan_ending.ended suppressed plan_id=%s channels=%s",
                plan_data.plan_id,
                ",".join(c.value for c in result.suppressed_channels),
            )

    def _handle_renewal_due(self, envelope: EventEnvelope) -> None:
        """Create a notification for a plan renewal due."""
        user_id = self._parse_user_id(envelope)
        plan_data = self._parse_plan_data(envelope)

        # Build deep link to plan renewal
        deep_link = f"nutriplan://plan/{plan_data.plan_id}/renew"

        # Build notification
        notification = Notification(
            user_id=user_id,
            type=NotificationType.PLAN_RENEWAL,
            payload={
                "planId": plan_data.plan_id,
                "planType": plan_data.plan_type,
                "renewalDate": plan_data.ending_date.isoformat(),
                "deepLink": deep_link,
                "occurredAt": envelope.occurred_at.isoformat(),
            },
            channels=self._channels,
        )

        result = self._recorder.record(notification, event_id=envelope.event_id)
        if result.recorded:
            logger.info(
                "plan_ending.renewal notification_recorded plan_id=%s user_id=%s",
                plan_data.plan_id,
                user_id,
            )
        elif result.duplicate:
            logger.info(
                "plan_ending.renewal duplicate plan_id=%s",
                plan_data.plan_id,
            )
        else:
            logger.info(
                "plan_ending.renewal suppressed plan_id=%s channels=%s",
                plan_data.plan_id,
                ",".join(c.value for c in result.suppressed_channels),
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

    def _parse_plan_data(self, envelope: EventEnvelope) -> PlanEndingPayload:
        """Parse plan ending data from the envelope."""
        plan_id = self._require_string(envelope.data, "planId")
        plan_type = self._require_string(envelope.data, "planType")
        ending_date_str = self._require_string(envelope.data, "endingDate")

        try:
            ending_date = datetime.fromisoformat(ending_date_str)
        except (ValueError, TypeError):
            raise MalformedEvent(
                f"event {envelope.event_id} ({envelope.type}) has invalid endingDate {ending_date_str!r}"
            ) from None

        return PlanEndingPayload(
            plan_id=plan_id,
            user_id=self._parse_user_id(envelope),
            plan_type=plan_type,
            ending_date=ending_date,
            deep_link=f"nutriplan://plan/{plan_id}/manage",
        )

    @staticmethod
    def _require_string(data: dict, key: str) -> str:
        """Require a string field in the data."""
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MalformedEvent(f"missing or invalid field: {key}")
        return value.strip()

    @property
    def notification_types(self) -> tuple[NotificationType, ...]:
        """Every notification type this consumer can produce."""
        return (
            NotificationType.PLAN_ENDING,
            NotificationType.PLAN_ENDED,
            NotificationType.PLAN_RENEWAL,
        )
