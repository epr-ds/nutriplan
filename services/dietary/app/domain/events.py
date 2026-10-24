"""Dietary reminder domain events.

The ``MealPlan`` aggregate *records* what happened to a plan the way any other aggregate does;
publishing the reminder side of that history is the reminder scheduler's concern (NTF-203), which
turns plan state into notification events for the notification service's bus.

Keeping each event a plain, immutable value object lets the aggregate stay free of any
transport/broker concern, and lets the scheduler be unit-tested against an in-process publisher
without touching a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.meal_plan import MealType


@dataclass(frozen=True)
class MealReminderDue:
    """A planned meal whose reminder moment has arrived (NTF-203).

    ``event_id`` is the producer's own event id -- the ``id`` inside the envelope the
    notification service consumes -- and is what makes a re-emitted reminder a no-op rather
    than a duplicate: the notification side dedupes on ``(event_id, user, type)``.
    """

    event_id: str
    meal_id: str
    user_id: str
    meal_type: MealType
    scheduled_time: datetime
    occurred_at: datetime
    meal_name: str | None = None


@dataclass(frozen=True)
class MealReminderCancelled:
    """A planned meal's reminder was withdrawn before it ever fired."""

    event_id: str
    meal_id: str
    user_id: str
    occurred_at: datetime


@dataclass(frozen=True)
class PlanEndingSoon:
    """A plan is about to end; the user should be told how to manage the remainder."""

    event_id: str
    plan_id: str
    user_id: str
    plan_type: str
    ending_date: datetime
    occurred_at: datetime


@dataclass(frozen=True)
class PlanEndingEnded:
    """A plan's window has closed; the user should be pointed at the summary."""

    event_id: str
    plan_id: str
    user_id: str
    plan_type: str
    ended_date: datetime
    occurred_at: datetime


# The closed set of events the reminder scheduler can publish. Kept as a union (rather than a
# base class) so each event stays a flat, frozen value object and exhaustive handling is
# checkable.
DomainEvent = MealReminderDue | MealReminderCancelled | PlanEndingSoon | PlanEndingEnded
