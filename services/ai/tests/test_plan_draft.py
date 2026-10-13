"""Unit tests for the optimized-plan draft and its diff metadata (AIA-405).

The optimize-plan use case never overwrites the user's plan: it returns a *draft* the user reviews
before committing. :class:`PlanDraft` wraps an :class:`OptimizationOutcome` into that reviewable
proposal — the proposed plan re-statused to ``draft`` (the original left untouched) plus a
:class:`PlanDiff` describing what changed (the goal metric's movement and per-meal serving edits)
so the UI can show a before/after. When the optimization didn't actually improve things (AIA-404's
no-op), the draft proposes the original unchanged and the diff is empty. These tests pin that
projection purely; the service wiring and acceptance are covered elsewhere.
"""

from __future__ import annotations

from datetime import date

from app.optimization.baseline import BaselineDirection, BaselineMetric, baseline_for
from app.optimization.commands import OptimizationGoal
from app.optimization.draft import MealServingChange, PlanDiff, PlanDraft
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.result import OptimizationOutcome

_GOAL = OptimizationGoal.INCREASE_PROTEIN


def _plan(*, protein: float, servings: float, status: str = "active") -> OptimizationPlan:
    nutrition = PlanNutrition(calories=400, protein=protein, carbs=45.0, fat=12.0, sugar=8.0)
    return OptimizationPlan(
        id="11111111-1111-1111-1111-111111111111",
        name="Cutting Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=2000,
        status=status,
        meals=(
            OptimizationMeal(
                id="m1", meal_type="breakfast", servings=servings, nutrition=nutrition
            ),
        ),
        nutritional_summary=PlanNutritionSummary(
            total=nutrition,
            daily_average=nutrition,
            targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
        ),
    )


def _outcome(*, original: OptimizationPlan, optimized: OptimizationPlan) -> OptimizationOutcome:
    return OptimizationOutcome(
        original=original,
        optimized=optimized,
        baseline=baseline_for(original, _GOAL),
        optimized_value=float(optimized.nutritional_summary.daily_average.protein),
    )


class TestPlanDiff:
    def test_captures_a_maximize_improvement(self) -> None:
        original = _plan(protein=20.0, servings=1.0)
        proposed = _plan(protein=30.0, servings=2.0)

        diff = PlanDiff.between(
            original, proposed, baseline=baseline_for(original, _GOAL), optimized_value=30.0
        )

        assert diff.goal is _GOAL
        assert diff.baseline_value == 20.0
        assert diff.optimized_value == 30.0
        assert diff.improvement == 10.0
        assert diff.improved is True

    def test_signs_a_minimize_improvement_positively(self) -> None:
        # For REDUCE_CALORIES, dropping the metric is the gain, so improvement stays positive.
        original = _plan(protein=20.0, servings=1.0)
        baseline = BaselineMetric(
            goal=OptimizationGoal.REDUCE_CALORIES,
            value=2000.0,
            direction=BaselineDirection.MINIMIZE,
        )

        diff = PlanDiff.between(original, original, baseline=baseline, optimized_value=1800.0)

        assert diff.improvement == 200.0
        assert diff.improved is True

    def test_a_tie_is_not_an_improvement(self) -> None:
        original = _plan(protein=20.0, servings=1.0)

        diff = PlanDiff.between(
            original, original, baseline=baseline_for(original, _GOAL), optimized_value=20.0
        )

        assert diff.improvement == 0.0
        assert diff.improved is False
        assert diff.meal_changes == ()
        assert diff.has_changes is False

    def test_records_only_meals_whose_servings_changed(self) -> None:
        original = _plan(protein=20.0, servings=1.0)
        proposed = _plan(protein=30.0, servings=2.5)

        diff = PlanDiff.between(
            original, proposed, baseline=baseline_for(original, _GOAL), optimized_value=30.0
        )

        assert diff.has_changes is True
        assert diff.meal_changes == (
            MealServingChange(
                meal_id="m1", meal_type="breakfast", previous_servings=1.0, new_servings=2.5
            ),
        )
        assert diff.meal_changes[0].delta == 1.5

    def test_unchanged_servings_produce_no_meal_changes(self) -> None:
        original = _plan(protein=20.0, servings=1.0)
        proposed = _plan(protein=30.0, servings=1.0)  # nutrition differs, servings do not

        diff = PlanDiff.between(
            original, proposed, baseline=baseline_for(original, _GOAL), optimized_value=30.0
        )

        assert diff.meal_changes == ()


class TestPlanDraftFromImprovedOutcome:
    def test_proposes_the_optimized_plan_as_a_draft(self) -> None:
        original = _plan(protein=20.0, servings=1.0, status="active")
        optimized = _plan(protein=30.0, servings=2.0, status="active")

        draft = PlanDraft.from_outcome(_outcome(original=original, optimized=optimized))

        assert draft.improved is True
        assert draft.plan is draft.proposed
        assert draft.proposed.status == "draft"
        assert draft.proposed.meals[0].servings == 2.0

    def test_leaves_the_original_untouched(self) -> None:
        original = _plan(protein=20.0, servings=1.0, status="active")
        optimized = _plan(protein=30.0, servings=2.0)

        draft = PlanDraft.from_outcome(_outcome(original=original, optimized=optimized))

        assert draft.original is original
        assert draft.original.status == "active"
        assert draft.original.meals[0].servings == 1.0

    def test_exposes_the_diff(self) -> None:
        original = _plan(protein=20.0, servings=1.0)
        optimized = _plan(protein=30.0, servings=2.0)

        draft = PlanDraft.from_outcome(_outcome(original=original, optimized=optimized))

        assert draft.diff.improved is True
        assert draft.diff.improvement == 10.0
        assert draft.diff.has_changes is True
        assert draft.diff.meal_changes[0].new_servings == 2.0


class TestPlanDraftFromNoOpOutcome:
    def test_proposes_the_original_unchanged(self) -> None:
        # AIA-404 returned the original (optimized was no better); there is nothing to draft.
        original = _plan(protein=20.0, servings=1.0, status="active")
        worse = _plan(protein=10.0, servings=0.5)

        draft = PlanDraft.from_outcome(_outcome(original=original, optimized=worse))

        assert draft.improved is False
        assert draft.plan is original
        assert draft.proposed is original
        assert draft.proposed.status == "active"

    def test_has_an_empty_diff_pinned_to_the_baseline(self) -> None:
        original = _plan(protein=20.0, servings=1.0)
        worse = _plan(protein=10.0, servings=0.5)

        draft = PlanDraft.from_outcome(_outcome(original=original, optimized=worse))

        assert draft.diff.meal_changes == ()
        assert draft.diff.has_changes is False
        assert draft.diff.optimized_value == draft.diff.baseline_value == 20.0
        assert draft.diff.improvement == 0.0
