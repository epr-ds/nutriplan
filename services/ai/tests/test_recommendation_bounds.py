"""Tests for nutrition-bounds enforcement: clamp targets, reject insane recipes (AIA-502).

The transport edge already rejects an out-of-range ``dailyCalorieTarget`` (AIA-201 schema), but the
use case must not trust its caller: it clamps the calorie targets to sane bounds (defense in depth,
and the per-meal target is otherwise unbounded) and -- crucially -- it screens the *model's* output,
which nothing upstream can validate. :class:`NutritionBoundsGuard` drops any recommended recipe
whose nutrition is not physically sane (non-positive/huge calories, negative macros, sugar over
carbs, or macros that cannot add up to the stated calories) and records every clamp and rejection
through a :class:`BoundsTelemetry` port. Everything here is pure -- no LLM, no I/O.
"""

from __future__ import annotations

import logging

from app.recommendations.bounds import (
    MAX_DAILY_CALORIES,
    MIN_DAILY_CALORIES,
    BoundsReason,
    BoundsViolation,
    CalorieClamp,
    InMemoryBoundsTelemetry,
    LoggingBoundsTelemetry,
    NutritionBoundsGuard,
)
from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


def _guard(telemetry: InMemoryBoundsTelemetry | None = None) -> NutritionBoundsGuard:
    return NutritionBoundsGuard(telemetry or InMemoryBoundsTelemetry())


def _command(*, daily: int | None = None, meal: int | None = None) -> RecommendationCommand:
    return RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        daily_calorie_target=daily,
        calorie_target=meal,
    )


def _recipe(
    calories: int,
    *,
    protein: int | None = None,
    carbs: int | None = None,
    fat: int | None = None,
    sugar: int | None = None,
    recipe_id: str = "r",
    name: str = "Recipe",
) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=recipe_id,
        name=name,
        servings=1,
        ingredients=(RecommendedIngredient(name="something"),),
        instructions=("Mix.",),
        nutrition=RecommendedNutrition(
            calories=calories, protein=protein, carbs=carbs, fat=fat, sugar=sugar
        ),
        source=RecipeSource.SYNTHESIZED,
    )


# --- target clamping -----------------------------------------------------------------------------


def test_clamps_daily_target_below_minimum_up_to_the_floor() -> None:
    telemetry = InMemoryBoundsTelemetry()

    clamped = _guard(telemetry).clamp(_command(daily=800))

    assert clamped.daily_calorie_target == MIN_DAILY_CALORIES
    assert telemetry.clamps == [
        CalorieClamp(field="daily_calorie_target", original=800, clamped=MIN_DAILY_CALORIES)
    ]


def test_clamps_daily_target_above_maximum_down_to_the_ceiling() -> None:
    clamped = _guard().clamp(_command(daily=9000))

    assert clamped.daily_calorie_target == MAX_DAILY_CALORIES


def test_leaves_an_in_range_daily_target_untouched_and_records_nothing() -> None:
    telemetry = InMemoryBoundsTelemetry()
    command = _command(daily=2000)

    clamped = _guard(telemetry).clamp(command)

    assert clamped is command
    assert telemetry.clamps == []


def test_caps_an_unbounded_per_meal_target_at_the_daily_maximum() -> None:
    telemetry = InMemoryBoundsTelemetry()

    clamped = _guard(telemetry).clamp(_command(meal=9000))

    assert clamped.calorie_target == MAX_DAILY_CALORIES
    assert telemetry.clamps[0].field == "calorie_target"


def test_leaves_a_reasonable_per_meal_target_untouched() -> None:
    command = _command(meal=700)

    assert _guard().clamp(command) is command


def test_clamps_both_targets_and_records_each() -> None:
    telemetry = InMemoryBoundsTelemetry()

    clamped = _guard(telemetry).clamp(_command(daily=100, meal=9000))

    assert clamped.daily_calorie_target == MIN_DAILY_CALORIES
    assert clamped.calorie_target == MAX_DAILY_CALORIES
    assert len(telemetry.clamps) == 2


# --- recipe macro sanity -------------------------------------------------------------------------


def test_keeps_a_physically_sane_recipe() -> None:
    telemetry = InMemoryBoundsTelemetry()
    # 4*30 + 4*50 + 9*20 = 500 kcal, exactly matching; sugar <= carbs.
    recipe = _recipe(500, protein=30, carbs=50, fat=20, sugar=10)

    kept = _guard(telemetry).enforce((recipe,))

    assert kept == (recipe,)
    assert telemetry.rejections == []


def test_rejects_non_positive_calories() -> None:
    telemetry = InMemoryBoundsTelemetry()

    kept = _guard(telemetry).enforce((_recipe(0, recipe_id="zero"),))

    assert kept == ()
    assert telemetry.rejections == [
        BoundsViolation(
            recipe_id="zero", recipe_name="Recipe", reason=BoundsReason.NON_POSITIVE_CALORIES
        )
    ]


def test_rejects_calories_above_the_daily_maximum() -> None:
    kept = _guard().enforce((_recipe(MAX_DAILY_CALORIES + 1),))

    assert kept == ()


def test_rejects_a_negative_macro() -> None:
    telemetry = InMemoryBoundsTelemetry()

    kept = _guard(telemetry).enforce((_recipe(500, protein=-5),))

    assert kept == ()
    assert telemetry.rejections[0].reason is BoundsReason.NEGATIVE_MACRO


def test_rejects_sugar_exceeding_carbs() -> None:
    telemetry = InMemoryBoundsTelemetry()

    kept = _guard(telemetry).enforce((_recipe(400, carbs=10, sugar=40),))

    assert kept == ()
    assert telemetry.rejections[0].reason is BoundsReason.SUGAR_EXCEEDS_CARBS


def test_rejects_macros_that_cannot_add_up_to_the_calories() -> None:
    telemetry = InMemoryBoundsTelemetry()
    # 4*100 + 4*100 + 9*100 = 1700 kcal, nowhere near the stated 200.
    kept = _guard(telemetry).enforce((_recipe(200, protein=100, carbs=100, fat=100),))

    assert kept == ()
    assert telemetry.rejections[0].reason is BoundsReason.MACRO_CALORIE_MISMATCH


def test_keeps_a_recipe_with_only_calories_reported() -> None:
    # With no macro breakdown there is nothing to cross-check, so a sane calorie count is kept.
    kept = _guard().enforce((_recipe(450),))

    assert len(kept) == 1


def test_tolerates_small_macro_calorie_discrepancies() -> None:
    # 4*30 + 4*55 + 9*20 = 520 kcal vs a stated 500: within tolerance, kept.
    kept = _guard().enforce((_recipe(500, protein=30, carbs=55, fat=20),))

    assert len(kept) == 1


def test_records_every_reason_a_recipe_is_rejected_for() -> None:
    telemetry = InMemoryBoundsTelemetry()

    _guard(telemetry).enforce((_recipe(0, protein=-5),))

    reasons = {violation.reason for violation in telemetry.rejections}
    assert reasons == {BoundsReason.NON_POSITIVE_CALORIES, BoundsReason.NEGATIVE_MACRO}


def test_drops_only_the_insane_recipes_and_preserves_order() -> None:
    telemetry = InMemoryBoundsTelemetry()
    good_one = _recipe(300, recipe_id="a", name="Good A")
    bad = _recipe(9000, recipe_id="b", name="Bad")
    good_two = _recipe(450, recipe_id="c", name="Good C")

    kept = _guard(telemetry).enforce((good_one, bad, good_two))

    assert [recipe.id for recipe in kept] == ["a", "c"]
    assert telemetry.rejection_count == 1


def test_guard_without_telemetry_still_enforces() -> None:
    kept = NutritionBoundsGuard().enforce((_recipe(9000),))

    assert kept == ()


def test_logging_telemetry_levels(caplog) -> None:
    telemetry = LoggingBoundsTelemetry()

    with caplog.at_level(logging.INFO, logger="app.recommendations.bounds"):
        telemetry.record_clamp(
            CalorieClamp(field="daily_calorie_target", original=800, clamped=1200)
        )
        telemetry.record_rejection(
            BoundsViolation(
                recipe_id="b", recipe_name="Bad", reason=BoundsReason.EXCESSIVE_CALORIES
            )
        )

    levels = {record.levelno for record in caplog.records}
    assert logging.INFO in levels
    assert logging.WARNING in levels
