"""DPL-105 application-layer tests: the add-meal-to-plan use case (Mongo-free)."""

from datetime import date

import pytest

from app.application.commands import AddMealToPlanCommand
from app.application.meal_service import MealService
from app.domain.errors import (
    InvalidServingsError,
    MealPlanNotFoundError,
    RecipeNotFoundError,
)
from app.domain.meal_plan import MealPlan, MealType
from app.domain.recipe import NutritionalInfo, Recipe
from tests.fakes import InMemoryMealPlanRepository, InMemoryRecipeRepository

RECIPE_ID = "recipe-1"


def _service(
    *, plan_owner: str = "owner"
) -> tuple[MealService, MealPlan, InMemoryMealPlanRepository]:
    plans = InMemoryMealPlanRepository()
    recipes = InMemoryRecipeRepository()
    recipes.add(
        Recipe.create(
            name="Oatmeal",
            servings=2,
            nutritional_info=NutritionalInfo(calories=320, protein=12.0),
        ).model_copy(update={"id": RECIPE_ID})
    )
    plan = MealPlan(
        user_id=plan_owner,
        name="Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )
    plans.add(plan)
    return MealService(plans, recipes), plan, plans


def _command(
    plan_id: str, *, user_id: str = "owner", recipe_id: str = RECIPE_ID, servings: float = 1.5
):
    return AddMealToPlanCommand(
        user_id=user_id,
        plan_id=plan_id,
        meal_type=MealType.BREAKFAST,
        recipe_id=recipe_id,
        servings=servings,
    )


def test_add_meal_persists_and_returns_meal_with_recipe():
    service, plan, plans = _service()

    meal, recipe = service.add_meal_to_plan(_command(plan.id))

    assert meal.recipe_id == RECIPE_ID
    assert meal.servings == 1.5
    assert recipe.id == RECIPE_ID
    assert recipe.name == "Oatmeal"
    # Mutation persisted to the (owner-scoped) repository.
    stored = plans.get("owner", plan.id)
    assert len(stored.meals) == 1
    assert stored.meals[0].recipe_id == RECIPE_ID


def test_add_meal_computes_and_persists_nutrition():
    # Recipe carries per-serving 320 cal / 12 g protein; a 1.5-serving meal scales that (DPL-301).
    service, plan, plans = _service()

    meal, _recipe = service.add_meal_to_plan(_command(plan.id, servings=1.5))

    assert meal.nutritional_info is not None
    assert meal.nutritional_info.calories == 480  # 320 * 1.5
    assert meal.nutritional_info.protein == 18.0  # 12.0 * 1.5
    # The computed nutrition is embedded on the persisted meal, not just the returned value.
    stored_meal = plans.get("owner", plan.id).meals[0]
    assert stored_meal.nutritional_info.calories == 480
    assert stored_meal.nutritional_info.protein == 18.0


def test_add_meal_unknown_plan_raises_not_found():
    service, _plan, _plans = _service()

    with pytest.raises(MealPlanNotFoundError):
        service.add_meal_to_plan(_command("does-not-exist"))


def test_add_meal_other_users_plan_raises_not_found():
    service, plan, _plans = _service(plan_owner="owner")

    with pytest.raises(MealPlanNotFoundError):
        service.add_meal_to_plan(_command(plan.id, user_id="intruder"))


def test_add_meal_unknown_recipe_raises_recipe_not_found():
    service, plan, plans = _service()

    with pytest.raises(RecipeNotFoundError):
        service.add_meal_to_plan(_command(plan.id, recipe_id="missing-recipe"))

    # Nothing persisted on failure.
    assert plans.get("owner", plan.id).meals == []


def test_add_meal_non_positive_servings_raises_invalid_servings():
    service, plan, plans = _service()

    with pytest.raises(InvalidServingsError):
        service.add_meal_to_plan(_command(plan.id, servings=0))

    assert plans.get("owner", plan.id).meals == []
