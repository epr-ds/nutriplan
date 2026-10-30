"""The versioned wire envelope for dietary reminder events (NTF-203).

Published events are wrapped in a small, self-describing envelope so the notification
service's consumer can route and evolve safely::

    {
      "schemaVersion": 1,
      "id": "<uuid4>",                 # unique per publish, for idempotent consumers
      "type": "meal.reminder.due",       # meal.reminder.* | plan.ending.*
      "occurredAt": "2026-10-24T21:00:00+00:00",
      "data": { ... }                  # camelCase, type-specific
    }

The ``type`` names the reminder the producer means: a meal whose scheduled moment arrived
(``meal.reminder.due``), a meal's reminder withdrawn before it fired (``meal.reminder.cancelled``),
a plan close enough to matter (``plan.ending.soon``), or a plan whose window closed
(``plan.ended``). Bumping :data:`SCHEMA_VERSION` is how the payload evolves without breaking
existing consumers.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.events import (
    DomainEvent,
    MealReminderCancelled,
    MealReminderDue,
    PlanEndingEnded,
    PlanEndingSoon,
)

SCHEMA_VERSION = 1

EVENT_TYPE_MEAL_REMINDER_DUE = "meal.reminder.due"
EVENT_TYPE_MEAL_REMINDER_CANCELLED = "meal.reminder.cancelled"
EVENT_TYPE_PLAN_ENDING_SOON = "plan.ending.soon"
EVENT_TYPE_PLAN_ENDED = "plan.ended"


def event_type(event: DomainEvent) -> str:
    """Map a reminder domain event to its bus event ``type``."""
    if isinstance(event, MealReminderDue):
        return EVENT_TYPE_MEAL_REMINDER_DUE
    if isinstance(event, MealReminderCancelled):
        return EVENT_TYPE_MEAL_REMINDER_CANCELLED
    if isinstance(event, PlanEndingSoon):
        return EVENT_TYPE_PLAN_ENDING_SOON
    if isinstance(event, PlanEndingEnded):
        return EVENT_TYPE_PLAN_ENDED
    raise ValueError(f"unsupported reminder domain event: {type(event).__name__}")


def _data(event: DomainEvent) -> dict[str, Any]:
    if isinstance(event, MealReminderDue):
        data: dict[str, Any] = {
            "userId": event.user_id,
            "mealId": event.meal_id,
            "mealType": event.meal_type.value,
            "scheduledTime": event.scheduled_time.isoformat(),
        }
        if event.meal_name is not None:
            data["mealName"] = event.meal_name
        return data
    if isinstance(event, MealReminderCancelled):
        return {"userId": event.user_id, "mealId": event.meal_id}
    if isinstance(event, PlanEndingSoon):
        return {
            "userId": event.user_id,
            "planId": event.plan_id,
            "planType": event.plan_type,
            "endingDate": event.ending_date.isoformat(),
        }
    return {
        "userId": event.user_id,
        "planId": event.plan_id,
        "planType": event.plan_type,
        "endingDate": event.ended_date.isoformat(),
    }


def to_envelope(event: DomainEvent, *, event_id: str | None = None) -> dict[str, Any]:
    """Serialize a reminder domain event to its versioned, JSON-native envelope.

    ``event_id`` is the producer's own event id and defaults to a fresh uuid4 per publish; the
    scheduler passes its deterministic per-aggregate ids so a rescheduled reminder is a no-op
    rather than a duplicate notification.
    """
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": event_id or str(uuid.uuid4()),
        "type": event_type(event),
        "occurredAt": event.occurred_at.isoformat(),
        "data": _data(event),
    }
