"""DPL-105: MealPlan.add_meal appends a planned meal and enforces servings > 0."""

from datetime import date

import pytest

from app.domain.errors import InvalidServingsError
from app.domain.meal_plan import MealPlan, MealType


def _draft_plan() -> MealPlan:
    return MealPlan(
        user_id="user-1",
        name="Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )


def test_add_meal_appends_and_returns_meal():
    plan = _draft_plan()
    before = plan.updated_at

    meal = plan.add_meal(meal_type=MealType.BREAKFAST, recipe_id="r1", servings=1.5)

    assert meal in plan.meals
    assert len(plan.meals) == 1
    assert meal.recipe_id == "r1"
    assert meal.servings == 1.5
    assert plan.meals[0].meal_type == MealType.BREAKFAST.value
    assert plan.updated_at >= before


def test_add_meal_assigns_a_meal_id():
    plan = _draft_plan()

    meal = plan.add_meal(meal_type=MealType.LUNCH, recipe_id="r2", servings=2)

    assert meal.id


def test_add_meal_rejects_zero_servings():
    plan = _draft_plan()

    with pytest.raises(InvalidServingsError):
        plan.add_meal(meal_type=MealType.DINNER, recipe_id="r3", servings=0)

    assert plan.meals == []


def test_add_meal_rejects_negative_servings():
    plan = _draft_plan()

    with pytest.raises(InvalidServingsError):
        plan.add_meal(meal_type=MealType.SNACK, recipe_id="r4", servings=-1.0)

    assert plan.meals == []
