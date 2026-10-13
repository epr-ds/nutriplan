"""Unit tests for the goal-directed constrained optimizer (AIA-403).

These pin the only edit AIA-403 makes — bounded, allergen-safe *serving* adjustments to the recipes
already in the plan — and the four supported goals. The optimizer is a deterministic greedy
hill-climb over those steps, scored by the AIA-402 ``measure_metric``; tests assert the metric moves
the right way, edits stay inside the serving policy, an excluded meal is never amplified, and an
unmeasurable or already-optimal plan is returned unchanged.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.optimization.baseline import measure_metric
from app.optimization.commands import OptimizationGoal
from app.optimization.optimizer import PlanOptimizer, ServingPolicy
from app.optimization.plan import (
    NutritionTargets,
    OptimizationConstraints,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)

_TARGETS = NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50)


def _meal(
    meal_id: str,
    *,
    meal_type: str = "lunch",
    servings: float = 1.0,
    calories: int = 500,
    protein: float = 30.0,
    carbs: float = 50.0,
    fat: float = 15.0,
    sugar: float = 10.0,
    ingredients: tuple[str, ...] = (),
) -> OptimizationMeal:
    return OptimizationMeal(
        id=meal_id,
        meal_type=meal_type,
        servings=servings,
        nutrition=PlanNutrition(
            calories=calories, protein=protein, carbs=carbs, fat=fat, sugar=sugar
        ),
        ingredients=ingredients,
    )


def _sum(meals: tuple[OptimizationMeal, ...]) -> PlanNutrition:
    return PlanNutrition(
        calories=sum(int(m.nutrition.calories or 0) for m in meals),
        protein=sum(float(m.nutrition.protein or 0.0) for m in meals),
        carbs=sum(float(m.nutrition.carbs or 0.0) for m in meals),
        fat=sum(float(m.nutrition.fat or 0.0) for m in meals),
        sugar=sum(float(m.nutrition.sugar or 0.0) for m in meals),
    )


def _plan(
    *meals: OptimizationMeal,
    constraints: OptimizationConstraints | None = None,
) -> OptimizationPlan:
    # A single-day plan, so daily_average == total and the goal metrics are easy to reason about.
    total = _sum(meals)
    return OptimizationPlan(
        id="11111111-1111-1111-1111-111111111111",
        name="Plan",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=2000,
        status="active",
        meals=meals,
        nutritional_summary=PlanNutritionSummary(
            total=total, daily_average=total, targets=_TARGETS
        ),
        constraints=constraints or OptimizationConstraints(),
    )


def _servings(plan: OptimizationPlan) -> dict[str, float]:
    return {meal.id: meal.servings for meal in plan.meals}


class TestServingEdits:
    def test_reduce_calories_lowers_average_calories(self) -> None:
        plan = _plan(_meal("m1", servings=2.0, calories=600))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.REDUCE_CALORIES)

        assert measure_metric(optimized, OptimizationGoal.REDUCE_CALORIES) < measure_metric(
            plan, OptimizationGoal.REDUCE_CALORIES
        )
        assert _servings(optimized)["m1"] < 2.0

    def test_increase_protein_raises_average_protein(self) -> None:
        plan = _plan(_meal("m1", servings=1.0, protein=30.0))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_PROTEIN)

        assert measure_metric(optimized, OptimizationGoal.INCREASE_PROTEIN) > measure_metric(
            plan, OptimizationGoal.INCREASE_PROTEIN
        )
        assert _servings(optimized)["m1"] > 1.0

    def test_balance_macros_raises_the_alignment_score(self) -> None:
        # Everything starts well under target, so dialing servings up improves alignment.
        plan = _plan(_meal("m1", servings=1.0, calories=400, protein=20.0, carbs=25.0, fat=8.0))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.BALANCE_MACROS)

        assert measure_metric(optimized, OptimizationGoal.BALANCE_MACROS) > measure_metric(
            plan, OptimizationGoal.BALANCE_MACROS
        )

    def test_increase_satisfaction_shifts_toward_the_protein_dense_meal(self) -> None:
        dense = _meal("dense", servings=1.0, calories=300, protein=40.0)
        empty = _meal("empty", servings=1.0, calories=600, protein=5.0)
        plan = _plan(dense, empty)

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_SATISFACTION)

        assert measure_metric(optimized, OptimizationGoal.INCREASE_SATISFACTION) > measure_metric(
            plan, OptimizationGoal.INCREASE_SATISFACTION
        )
        # The satiety proxy improves by favouring the dense meal over the empty one.
        assert _servings(optimized)["dense"] >= _servings(optimized)["empty"]


class TestConstraints:
    def test_keeps_servings_within_the_policy_bounds(self) -> None:
        policy = ServingPolicy(minimum=1.0, maximum=2.0, step=0.5)
        plan = _plan(_meal("m1", servings=1.5, protein=30.0))

        optimized = PlanOptimizer(policy).optimize(plan, OptimizationGoal.INCREASE_PROTEIN)

        assert 1.0 <= _servings(optimized)["m1"] <= 2.0

    def test_scales_nutrition_proportionally_with_servings(self) -> None:
        plan = _plan(_meal("m1", servings=1.0, calories=400, protein=20.0))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_PROTEIN)
        meal = optimized.meals[0]

        # Per-serving nutrition is preserved: the recipe is unchanged, only its servings.
        assert meal.nutrition.protein / meal.servings == pytest.approx(20.0)
        assert meal.nutrition.calories / meal.servings == pytest.approx(400.0, rel=0.05)

    def test_never_amplifies_a_meal_with_an_excluded_ingredient(self) -> None:
        # The protein-richest meal is off-limits (peanuts); the optimizer must grow the other one.
        peanut = _meal("peanut", servings=1.0, protein=50.0, ingredients=("Peanuts", "Honey"))
        safe = _meal("safe", servings=1.0, protein=25.0, ingredients=("Chicken",))
        plan = _plan(peanut, safe, constraints=OptimizationConstraints(allergies=("peanuts",)))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_PROTEIN)

        assert _servings(optimized)["peanut"] == 1.0
        assert _servings(optimized)["safe"] > 1.0

    def test_may_still_reduce_an_excluded_meal_when_that_helps(self) -> None:
        peanut = _meal("peanut", servings=2.0, calories=700, ingredients=("peanuts",))
        plan = _plan(peanut, constraints=OptimizationConstraints(excluded_ingredients=("Peanuts",)))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.REDUCE_CALORIES)

        assert _servings(optimized)["peanut"] < 2.0


class TestNoOpAndPurity:
    def test_returns_the_plan_unchanged_when_there_is_no_summary(self) -> None:
        plan = OptimizationPlan(
            id="p",
            name="Bare",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            daily_calorie_target=1800,
            status="draft",
        )

        assert PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_PROTEIN) is plan

    def test_single_meal_satisfaction_is_a_no_op(self) -> None:
        # Scaling one recipe's servings cannot change its protein-per-calorie density.
        plan = _plan(_meal("m1", servings=1.0, calories=400, protein=20.0))

        optimized = PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_SATISFACTION)

        assert _servings(optimized) == {"m1": 1.0}

    def test_is_deterministic(self) -> None:
        plan = _plan(_meal("m1", servings=1.0), _meal("m2", servings=1.0, protein=45.0))
        optimizer = PlanOptimizer()

        first = optimizer.optimize(plan, OptimizationGoal.INCREASE_PROTEIN)
        second = optimizer.optimize(plan, OptimizationGoal.INCREASE_PROTEIN)

        assert _servings(first) == _servings(second)

    def test_does_not_mutate_the_original_plan(self) -> None:
        plan = _plan(_meal("m1", servings=1.0, protein=30.0))

        PlanOptimizer().optimize(plan, OptimizationGoal.INCREASE_PROTEIN)

        assert plan.meals[0].servings == 1.0
        assert plan.nutritional_summary.daily_average.protein == 30.0
