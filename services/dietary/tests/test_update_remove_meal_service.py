"""DPL-107 application-layer tests: update/remove a planned meal (Mongo-free)."""

from datetime import date

import pytest

from app.application.commands import RemoveMealFromPlanCommand, UpdateMealInPlanCommand
from app.application.meal_service import MealService
from app.domain.errors import MealNotFoundError, MealPlanNotFoundError
from app.domain.meal_plan import MealPlan, MealType
from app.domain.recipe import NutritionalInfo, Recipe
from tests.fakes import InMemoryMealPlanRepository, InMemoryRecipeRepository

RECIPE_ID = "11111111-1111-1111-1111-111111111111"


def _recipes() -> InMemoryRecipeRepository:
    repo = InMemoryRecipeRepository()
    repo.add(
        Recipe.create(
            name="Protein Oats",
            servings=2,
            nutritional_info=NutritionalInfo(calories=420, protein=30.0),
        ).model_copy(update={"id": RECIPE_ID})
    )
    return repo


def _plans_with_meal() -> tuple[InMemoryMealPlanRepository, MealPlan, str]:
    plans = InMemoryMealPlanRepository()
    plan = MealPlan(
        user_id="user-1",
        name="Cutting",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )
    meal = plan.add_meal(meal_type=MealType.BREAKFAST, recipe_id=RECIPE_ID, servings=1.0)
    plans.add(plan)
    return plans, plan, meal.id


def _service(plans: InMemoryMealPlanRepository) -> MealService:
    return MealService(plans, _recipes())


def test_update_meal_recomputes_nutrition_for_new_servings():
    plans, plan, meal_id = _plans_with_meal()

    meal, recipe = _service(plans).update_meal(
        UpdateMealInPlanCommand(user_id="user-1", plan_id=plan.id, meal_id=meal_id, servings=1.5)
    )

    assert meal.servings == 1.5
    assert recipe is not None and recipe.id == RECIPE_ID
    # 420 cal / 30 g protein per serving scaled to 1.5 servings (DPL-301).
    assert meal.nutritional_info is not None
    assert meal.nutritional_info.calories == 630
    assert meal.nutritional_info.protein == 45.0
    # Persisted.
    assert plans.get("user-1", plan.id).find_meal(meal_id).servings == 1.5


def test_update_meal_day_only_does_not_touch_recipe():
    plans, plan, meal_id = _plans_with_meal()

    meal, recipe = _service(plans).update_meal(
        UpdateMealInPlanCommand(user_id="user-1", plan_id=plan.id, meal_id=meal_id, day_index=3)
    )

    assert meal.day_index == 3
    assert recipe is None


def test_update_meal_unknown_plan_raises_not_found():
    plans, _, meal_id = _plans_with_meal()

    with pytest.raises(MealPlanNotFoundError):
        _service(plans).update_meal(
            UpdateMealInPlanCommand(
                user_id="user-1", plan_id="missing", meal_id=meal_id, servings=2
            )
        )


def test_update_meal_unknown_meal_raises_not_found():
    plans, plan, _ = _plans_with_meal()

    with pytest.raises(MealNotFoundError):
        _service(plans).update_meal(
            UpdateMealInPlanCommand(
                user_id="user-1", plan_id=plan.id, meal_id="missing", servings=2
            )
        )


def test_remove_meal_removes_from_persisted_plan():
    plans, plan, meal_id = _plans_with_meal()

    _service(plans).remove_meal(
        RemoveMealFromPlanCommand(user_id="user-1", plan_id=plan.id, meal_id=meal_id)
    )

    assert plans.get("user-1", plan.id).meals == []


def test_remove_meal_unknown_meal_raises_not_found():
    plans, plan, _ = _plans_with_meal()

    with pytest.raises(MealNotFoundError):
        _service(plans).remove_meal(
            RemoveMealFromPlanCommand(user_id="user-1", plan_id=plan.id, meal_id="missing")
        )

    assert len(plans.get("user-1", plan.id).meals) == 1


def test_remove_meal_unknown_plan_raises_not_found():
    plans, _, meal_id = _plans_with_meal()

    with pytest.raises(MealPlanNotFoundError):
        _service(plans).remove_meal(
            RemoveMealFromPlanCommand(user_id="user-1", plan_id="missing", meal_id=meal_id)
        )
