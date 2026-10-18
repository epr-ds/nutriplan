"""DPL-705: golden-dataset accuracy tests for per-meal and plan-summary nutrition.

Loads ``tests/fixtures/nutrition_golden.json`` — a fixed dataset whose expected numbers are
hand-derived from the DPL-301/302/303 rules — and asserts the implementation reproduces them
exactly. The cases deliberately hit the half-up rounding boundaries (``.x5`` / ``.xx5``) and both
nutrition sources (an authored per-serving ``nutritionalInfo`` and an ingredient-derived recipe),
so a regression in the math or the rounding rule fails here even if the unit tests are refactored.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.domain.meal_plan import (
    MacroTargets,
    MealPlan,
    MealType,
    PlannedMeal,
)
from app.domain.nutrition import compute_meal_nutrition, summarize_plan_nutrition
from app.domain.recipe import Ingredient, Recipe
from app.domain.recipe import NutritionalInfo as RecipeNutritionalInfo

_FIXTURE = Path(__file__).parent / "fixtures" / "nutrition_golden.json"
_FIELDS = ("calories", "protein", "carbs", "fat", "sugar")


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(_FIXTURE.read_text())


def _build_recipe(raw: dict) -> Recipe:
    kwargs: dict = {"name": raw["name"], "servings": raw["servings"]}
    if "nutritionalInfo" in raw:
        kwargs["nutritional_info"] = RecipeNutritionalInfo(**raw["nutritionalInfo"])
    if "ingredients" in raw:
        kwargs["ingredients"] = [Ingredient(**ingredient) for ingredient in raw["ingredients"]]
    return Recipe.create(**kwargs).model_copy(update={"id": raw["id"]})


def _assert_nutrients(actual: object, expected: dict) -> None:
    for field in _FIELDS:
        assert getattr(actual, field) == pytest.approx(expected[field]), field


def _plan_from_golden(golden: dict) -> MealPlan:
    recipes = {raw["id"]: _build_recipe(raw) for raw in golden["recipes"]}
    plan_raw = golden["plan"]

    meals = []
    for meal_raw in plan_raw["meals"]:
        recipe = recipes[meal_raw["recipeId"]]
        info = compute_meal_nutrition(recipe, meal_raw["servings"])
        _assert_nutrients(info, meal_raw["expected"])
        meals.append(
            PlannedMeal(
                meal_type=MealType(meal_raw["mealType"]),
                recipe_id=recipe.id,
                servings=meal_raw["servings"],
                nutritional_info=info,
            )
        )

    macros = plan_raw["macroTargets"]
    return MealPlan(
        user_id="golden-user",
        name="Golden Plan",
        start_date=date.fromisoformat(plan_raw["startDate"]),
        end_date=date.fromisoformat(plan_raw["endDate"]),
        daily_calorie_target=plan_raw["dailyCalorieTarget"],
        macro_targets=MacroTargets(
            protein_grams=macros["proteinGrams"],
            carbs_grams=macros["carbsGrams"],
            fat_grams=macros["fatGrams"],
            sugar_grams=macros["sugarGrams"],
        ),
        meals=meals,
    )


def test_per_meal_nutrition_matches_golden(golden):
    # _plan_from_golden already asserts each meal against its expected values.
    _plan_from_golden(golden)


def test_plan_summary_totals_and_daily_average_match_golden(golden):
    summary = summarize_plan_nutrition(_plan_from_golden(golden))
    expected = golden["expectedSummary"]

    _assert_nutrients(summary.total, expected["total"])
    _assert_nutrients(summary.daily_average, expected["dailyAverage"])
    _assert_nutrients(summary.targets, expected["targets"])


def test_plan_progress_matches_golden(golden):
    summary = summarize_plan_nutrition(_plan_from_golden(golden))
    expected = golden["expectedSummary"]["progress"]

    for nutrient, want in expected.items():
        got = getattr(summary.progress, nutrient)
        assert got.target == want["target"], nutrient
        assert got.actual == pytest.approx(want["actual"]), nutrient
        assert got.percent_of_target == pytest.approx(want["percentOfTarget"]), nutrient
        assert got.status == want["status"], nutrient


def test_golden_rounding_boundaries_are_half_up(golden):
    # Pin the exact half-up cases baked into the fixture, so the fixtures cannot silently drift
    # into "whatever the code happens to produce".
    recipes = {raw["id"]: _build_recipe(raw) for raw in golden["recipes"]}

    # 207 * 1.5 = 310.5 -> 311 (energy whole, half up); 11.25 * 1.5 = 16.875 -> 16.9.
    oats = compute_meal_nutrition(recipes["r-oats"], 1.5)
    assert oats.calories == 311
    assert oats.protein == 16.9
    assert oats.sugar == 10.0  # 6.65 * 1.5 = 9.975 -> 10.0

    # Ingredient-derived: (500+360)/4 * 2.5 = 537.5 -> 538; (10+8)/4 * 2.5 = 11.25 -> 11.3.
    rice = compute_meal_nutrition(recipes["r-rice"], 2.5)
    assert rice.calories == 538
    assert rice.protein == 11.3
    assert rice.carbs == 112.5
