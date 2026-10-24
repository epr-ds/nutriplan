"""Turn meal plans into reminder events for the notification bus (NTF-203).

The scheduler is the producer half of the reminder loop the notification service consumes
(NTF-202 / NTF-602): it reads an active plan's planned meals and its end date and decides what
should be told the user, right now, through the publisher port. The notification service's
consumer already owns the shape of a ``meal.reminder.*`` / ``plan.ending.*`` notification; this
module owns the "should this fire?" decision and keeps it in one auditable place instead of
scattering "remind me about this meal" logic across the plan mutations.

Design calls (steered, NTF-203):

* **Meal-time reminders** fire per planned meal at a per-meal-type default time on the day the
  plan scheduled the meal for (``dayIndex`` inside ``startDate``). A meal whose moment has
  already passed emits ``meal.reminder.due``; a future one waits for the scheduler to run again
  on the next plan change or, in production, on the reminder tick.
* **Plan-ending reminders** emit ``plan.ending.soon`` within a short window of the plan's end
  date and ``plan.ended`` once the window has closed.
* **Idempotency** comes from deterministic event ids per aggregate instance and meal, so a
  reschedule that re-emits the same reminder is a no-op downstream rather than a duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from app.domain.events import (
    DomainEvent,
    MealReminderDue,
    PlanEndingEnded,
    PlanEndingSoon,
)
from app.domain.meal_plan import MealPlan, MealPlanStatus
from app.events.publisher import EventPublisher

DEFAULT_MEAL_REMINDER_TIMES: dict[str, time] = {
    "breakfast": time(8, 0),
    "lunch": time(13, 0),
    "dinner": time(19, 0),
    "snack": time(16, 0),
}
"""Per-meal-type default reminder times, UTC. Meal plans do not carry a per-meal time of
their own yet -- :class:`~app.domain.meal_plan.PlannedMeal` times a meal by its ``dayIndex``
inside the plan window -- so the cadence is a policy table the scheduler reads."""

DEFAULT_SOON_WINDOW_DAYS = 3
"""How close to a plan's end date the ``plan.ending.soon`` nudge fires (in days)."""


class PlanReminderScheduler:
    """Publish the reminder events an active meal plan calls for."""

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def emit(self, plan: MealPlan, *, now: datetime) -> list[DomainEvent]:
        """Publish this plan's reminder events at ``now``; return what was published."""
        events = self.reminder_events(plan, now=now)
        for event in events:
            self._publisher.publish(event)
        return events

    def reminder_events(self, plan: MealPlan, *, now: datetime) -> list[DomainEvent]:
        """The reminder events *plan* calls for at ``now``."""
        events: list[DomainEvent] = []

        if plan.status == MealPlanStatus.ACTIVE:
            for meal in plan.meals:
                moment = self._meal_moment(plan, meal)
                if moment is None or moment > now:
                    continue
                events.append(
                    MealReminderDue(
                        event_id=f"meal-reminder:{plan.id}:{meal.id}",
                        meal_id=meal.id,
                        user_id=plan.user_id,
                        meal_type=meal.meal_type,
                        meal_name=None,
                        scheduled_time=moment,
                        occurred_at=now,
                    )
                )

        ending = datetime.combine(plan.end_date, time.min, tzinfo=UTC)
        if plan.status in (
            MealPlanStatus.ACTIVE,
            MealPlanStatus.COMPLETED,
            MealPlanStatus.SAVED,
        ):
            if now >= ending:
                events.append(
                    PlanEndingEnded(
                        event_id=f"plan-ending:{plan.id}",
                        plan_id=plan.id,
                        user_id=plan.user_id,
                        plan_type=str(plan.dietary_type) if plan.dietary_type else "weekly",
                        ended_date=ending,
                        occurred_at=now,
                    )
                )
            elif ending - now <= timedelta(days=DEFAULT_SOON_WINDOW_DAYS):
                events.append(
                    PlanEndingSoon(
                        event_id=f"plan-ending-soon:{plan.id}",
                        plan_id=plan.id,
                        user_id=plan.user_id,
                        plan_type=str(plan.dietary_type) if plan.dietary_type else "weekly",
                        ending_date=ending,
                        occurred_at=now,
                    )
                )
        return events

    def _meal_moment(self, plan: MealPlan, meal) -> datetime | None:
        """When *meal* fires: ``startDate + dayIndex`` at the meal type's default time."""
        if meal.day_index is None:
            return None
        day = plan.start_date + timedelta(days=meal.day_index)
        return datetime.combine(
            day,
            DEFAULT_MEAL_REMINDER_TIMES.get(str(meal.meal_type), time(9, 0)),
            tzinfo=UTC,
        )
