"""DPL-107 / DPL-304: update_meal / remove_meal edit embedded meals and enforce their invariants."""

from datetime import date

import pytest

from app.domain.errors import (
    InvalidSatisfactionLevelError,
    InvalidServingsError,
    MealDayOutOfRangeError,
    MealNotFoundError,
)
from app.domain.meal_plan import MealPlan, MealType, NutritionalInfo


def _plan_with_meal() -> tuple[MealPlan, str]:
    plan = MealPlan(
        user_id="user-1",
        name="Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )
    meal = plan.add_meal(meal_type=MealType.BREAKFAST, recipe_id="r1", servings=1.0)
    return plan, meal.id


def test_update_meal_changes_servings_and_bumps_updated_at():
    plan, meal_id = _plan_with_meal()
    before = plan.updated_at

    updated = plan.update_meal(
        meal_id, servings=2.5, nutritional_info=NutritionalInfo(calories=500)
    )

    assert updated.servings == 2.5
    assert updated.nutritional_info is not None
    assert updated.nutritional_info.calories == 500
    assert plan.updated_at >= before


def test_update_meal_assigns_a_day_within_range():
    plan, meal_id = _plan_with_meal()

    updated = plan.update_meal(meal_id, day_index=6)  # last of 7 days

    assert updated.day_index == 6


def test_update_meal_rejects_day_outside_range():
    plan, meal_id = _plan_with_meal()

    with pytest.raises(MealDayOutOfRangeError):
        plan.update_meal(meal_id, day_index=7)  # one past the last day

    assert plan.find_meal(meal_id).day_index is None


@pytest.mark.parametrize("servings", [0, -1])
def test_update_meal_rejects_non_positive_servings(servings):
    plan, meal_id = _plan_with_meal()

    with pytest.raises(InvalidServingsError):
        plan.update_meal(meal_id, servings=servings)

    assert plan.find_meal(meal_id).servings == 1.0


def test_update_meal_unknown_meal_raises_not_found():
    plan, _ = _plan_with_meal()

    with pytest.raises(MealNotFoundError):
        plan.update_meal("no-such-meal", servings=2)


def test_update_meal_records_satisfaction_level():
    plan, meal_id = _plan_with_meal()

    updated = plan.update_meal(meal_id, satisfaction_level=4)

    assert updated.satisfaction_level == 4


@pytest.mark.parametrize("level", [0, 6, -1])
def test_update_meal_rejects_satisfaction_outside_1_to_5(level):
    plan, meal_id = _plan_with_meal()

    with pytest.raises(InvalidSatisfactionLevelError):
        plan.update_meal(meal_id, satisfaction_level=level)

    assert plan.find_meal(meal_id).satisfaction_level is None


def test_remove_meal_removes_and_bumps_updated_at():
    plan, meal_id = _plan_with_meal()
    before = plan.updated_at

    plan.remove_meal(meal_id)

    assert plan.meals == []
    assert plan.updated_at >= before


def test_remove_meal_unknown_meal_raises_not_found():
    plan, _ = _plan_with_meal()

    with pytest.raises(MealNotFoundError):
        plan.remove_meal("no-such-meal")

    assert len(plan.meals) == 1
