"""Unit tests for plan baseline metrics (AIA-402).

Before optimizing, the AI service measures the plan: it derives a single scalar metric for the
requested goal from the plan's nutritional summary (reusing the P2 nutrition totals) and records the
direction that counts as "better". AIA-404 re-measures the optimized plan with the same function and
asks the baseline whether it improved, returning the original on a tie or regression (safe no-op).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.optimization.baseline import (
    BaselineDirection,
    BaselineMetric,
    baseline_for,
    measure_metric,
    metric_direction,
)
from app.optimization.commands import OptimizationGoal
from app.optimization.plan import (
    NutritionTargets,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)

_BALANCED = PlanNutrition(calories=2000, protein=150.0, carbs=200.0, fat=60.0, sugar=40.0)
_TARGETS = NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=40)


def _plan(
    *,
    daily: PlanNutrition | None = None,
    targets: NutritionTargets | None = None,
    summary: bool = True,
) -> OptimizationPlan:
    daily = daily if daily is not None else _BALANCED
    targets = targets if targets is not None else _TARGETS
    nutritional_summary = (
        PlanNutritionSummary(total=daily, daily_average=daily, targets=targets) if summary else None
    )
    return OptimizationPlan(
        id="p1",
        name="Plan",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=2000,
        status="active",
        nutritional_summary=nutritional_summary,
    )


class TestMeasureMetric:
    def test_increase_protein_is_the_daily_average_protein(self) -> None:
        assert measure_metric(_plan(), OptimizationGoal.INCREASE_PROTEIN) == 150.0

    def test_reduce_calories_is_the_daily_average_calories(self) -> None:
        assert measure_metric(_plan(), OptimizationGoal.REDUCE_CALORIES) == 2000.0

    def test_increase_satisfaction_is_protein_density_per_1000_kcal(self) -> None:
        # 150 g protein over 2000 kcal -> 75 g per 1000 kcal (a satiety proxy).
        assert measure_metric(_plan(), OptimizationGoal.INCREASE_SATISFACTION) == pytest.approx(
            75.0
        )

    def test_balance_macros_is_one_when_the_average_hits_every_target(self) -> None:
        assert measure_metric(_plan(), OptimizationGoal.BALANCE_MACROS) == pytest.approx(1.0)

    def test_balance_macros_drops_when_a_macro_is_far_off_target(self) -> None:
        skewed = _plan(
            daily=PlanNutrition(calories=2000, protein=50.0, carbs=200.0, fat=60.0, sugar=40.0)
        )

        balanced = measure_metric(_plan(), OptimizationGoal.BALANCE_MACROS)
        off = measure_metric(skewed, OptimizationGoal.BALANCE_MACROS)

        assert off < balanced

    def test_a_missing_summary_degrades_every_metric_to_zero(self) -> None:
        plan = _plan(summary=False)

        assert measure_metric(plan, OptimizationGoal.INCREASE_PROTEIN) == 0.0
        assert measure_metric(plan, OptimizationGoal.REDUCE_CALORIES) == 0.0
        assert measure_metric(plan, OptimizationGoal.INCREASE_SATISFACTION) == 0.0
        assert measure_metric(plan, OptimizationGoal.BALANCE_MACROS) == 0.0

    def test_an_unknown_nutrient_degrades_to_zero(self) -> None:
        plan = _plan(daily=PlanNutrition(calories=2000, protein=None))

        assert measure_metric(plan, OptimizationGoal.INCREASE_PROTEIN) == 0.0

    def test_satisfaction_is_zero_when_calories_are_unknown_or_zero(self) -> None:
        plan = _plan(daily=PlanNutrition(calories=0, protein=150.0))

        assert measure_metric(plan, OptimizationGoal.INCREASE_SATISFACTION) == 0.0


class TestBaselineFor:
    @pytest.mark.parametrize(
        ("goal", "direction"),
        [
            (OptimizationGoal.INCREASE_PROTEIN, BaselineDirection.MAXIMIZE),
            (OptimizationGoal.REDUCE_CALORIES, BaselineDirection.MINIMIZE),
            (OptimizationGoal.INCREASE_SATISFACTION, BaselineDirection.MAXIMIZE),
            (OptimizationGoal.BALANCE_MACROS, BaselineDirection.MAXIMIZE),
        ],
    )
    def test_carries_the_goal_value_and_direction(
        self, goal: OptimizationGoal, direction: BaselineDirection
    ) -> None:
        baseline = baseline_for(_plan(), goal)

        assert baseline.goal is goal
        assert baseline.direction is direction
        assert baseline.value == measure_metric(_plan(), goal)


class TestImprovesOn:
    def test_maximize_requires_a_strictly_higher_candidate(self) -> None:
        baseline = BaselineMetric(
            goal=OptimizationGoal.INCREASE_PROTEIN,
            value=100.0,
            direction=BaselineDirection.MAXIMIZE,
        )

        assert baseline.improves_on(120.0) is True
        assert baseline.improves_on(100.0) is False
        assert baseline.improves_on(90.0) is False

    def test_minimize_requires_a_strictly_lower_candidate(self) -> None:
        baseline = BaselineMetric(
            goal=OptimizationGoal.REDUCE_CALORIES,
            value=2000.0,
            direction=BaselineDirection.MINIMIZE,
        )

        assert baseline.improves_on(1800.0) is True
        assert baseline.improves_on(2000.0) is False
        assert baseline.improves_on(2200.0) is False


class TestMetricDirection:
    @pytest.mark.parametrize(
        ("goal", "direction"),
        [
            (OptimizationGoal.INCREASE_PROTEIN, BaselineDirection.MAXIMIZE),
            (OptimizationGoal.REDUCE_CALORIES, BaselineDirection.MINIMIZE),
            (OptimizationGoal.INCREASE_SATISFACTION, BaselineDirection.MAXIMIZE),
            (OptimizationGoal.BALANCE_MACROS, BaselineDirection.MAXIMIZE),
        ],
    )
    def test_exposes_each_goal_direction_for_the_optimizer(
        self, goal: OptimizationGoal, direction: BaselineDirection
    ) -> None:
        assert metric_direction(goal) is direction
