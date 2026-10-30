"""NTF-203: turn a meal plan into the reminder events the notification service consumes."""

from datetime import UTC, date, datetime, time

from app.application.plan_reminder_scheduler import (
    DEFAULT_MEAL_REMINDER_TIMES,
    DEFAULT_SOON_WINDOW_DAYS,
    PlanReminderScheduler,
)
from app.domain.events import MealReminderDue, PlanEndingEnded, PlanEndingSoon
from app.domain.meal_plan import MealPlan, MealPlanStatus, MealType, PlannedMeal
from app.events.memory import InMemoryEventPublisher


def _planned_meal(meal_type: MealType = MealType.BREAKFAST, day_index: int = 0) -> PlannedMeal:
    return PlannedMeal(
        id=f"meal-{day_index}",
        meal_type=meal_type,
        recipe_id="recipe-1",
        servings=1.0,
        day_index=day_index,
    )


def _plan(
    *,
    status: MealPlanStatus = MealPlanStatus.ACTIVE,
    start_date: date = date(2026, 10, 24),
    end_date: date = date(2026, 11, 7),
    meals: list[PlannedMeal] | None = None,
) -> MealPlan:
    return MealPlan(
        id="plan-1",
        user_id="user-1",
        name="Week",
        start_date=start_date,
        end_date=end_date,
        daily_calorie_target=2000,
        status=status,
        meals=meals or [],
        dietary_type=None,
    )


NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def _scheduler_with_recorder() -> tuple[PlanReminderScheduler, InMemoryEventPublisher]:
    publisher = InMemoryEventPublisher()
    return PlanReminderScheduler(publisher), publisher


class TestMealReminders:
    def test_a_planned_meal_whose_moment_has_passed_emits_a_due_reminder(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(meals=[_planned_meal(day_index=0)])

        events = scheduler.emit(plan, now=NOW)

        assert len(events) == 1
        due = events[0]
        assert isinstance(due, MealReminderDue)
        assert due.event_id == "meal-reminder:plan-1:meal-0"
        assert due.user_id == "user-1"
        assert due.meal_id == "meal-0"
        assert due.meal_type == MealType.BREAKFAST
        assert due.scheduled_time == datetime(2026, 10, 24, 8, 0, tzinfo=UTC)
        assert due.occurred_at == NOW
        assert publisher.published == events

    def test_a_future_meal_does_not_emit_a_due_reminder_yet(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(start_date=date(2026, 10, 25), meals=[_planned_meal(day_index=0)])

        assert scheduler.emit(plan, now=NOW) == []

    def test_an_inactive_plan_emits_no_meal_reminder(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(status=MealPlanStatus.DRAFT, meals=[_planned_meal(day_index=0)])

        assert scheduler.emit(plan, now=NOW) == []


class TestPlanEndings:
    def test_a_plan_ending_inside_the_soon_window_emits_soon(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(end_date=date(2026, 10, 27))

        events = scheduler.emit(plan, now=NOW)

        assert len(events) == 1
        soon = events[0]
        assert isinstance(soon, PlanEndingSoon)
        assert soon.event_id == "plan-ending-soon:plan-1"
        assert soon.plan_id == "plan-1"
        assert soon.user_id == "user-1"
        assert soon.ending_date == datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
        assert soon.occurred_at == NOW

    def test_a_plan_ending_past_its_window_emits_ended(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(end_date=date(2026, 10, 20))

        events = scheduler.emit(plan, now=NOW)

        assert len(events) == 1
        ended = events[0]
        assert isinstance(ended, PlanEndingEnded)
        assert ended.event_id == "plan-ending:plan-1"
        assert ended.plan_id == "plan-1"
        assert ended.ended_date == datetime(2026, 10, 20, 0, 0, tzinfo=UTC)

    def test_a_plan_ending_far_away_in_the_future_emits_nothing(self) -> None:
        scheduler, publisher = _scheduler_with_recorder()
        plan = _plan(end_date=date(2027, 5, 1))

        assert scheduler.emit(plan, now=NOW) == []

    def test_the_soon_window_is_configured(self) -> None:
        assert DEFAULT_SOON_WINDOW_DAYS == 3
        assert DEFAULT_MEAL_REMINDER_TIMES == {
            "breakfast": time(8, 0),
            "lunch": time(13, 0),
            "dinner": time(19, 0),
            "snack": time(16, 0),
        }
