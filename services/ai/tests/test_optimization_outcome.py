"""Unit tests for the measurable-improvement check (AIA-404).

The optimize-plan use case must *provably* improve the plan or safely no-op: the optimized plan is
returned only when its goal metric beats the baseline, otherwise the original is returned unchanged.
:class:`OptimizationOutcome` owns that decision — given the original, the optimized plan, the
baseline, and the optimized plan's re-measured metric, it derives ``improved`` and the ``plan`` to
return. These tests pin that policy directly (the service's wiring is covered separately).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.optimization.baseline import BaselineDirection, BaselineMetric
from app.optimization.commands import OptimizationGoal
from app.optimization.plan import OptimizationPlan
from app.optimization.result import OptimizationOutcome


def _plan(name: str) -> OptimizationPlan:
    return OptimizationPlan(
        id="11111111-1111-1111-1111-111111111111",
        name=name,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=2000,
        status="active",
    )


_ORIGINAL = _plan("Original")
_OPTIMIZED = _plan("Optimized")


def _outcome(
    *,
    direction: BaselineDirection,
    baseline_value: float,
    optimized_value: float,
    goal: OptimizationGoal = OptimizationGoal.INCREASE_PROTEIN,
) -> OptimizationOutcome:
    return OptimizationOutcome(
        original=_ORIGINAL,
        optimized=_OPTIMIZED,
        baseline=BaselineMetric(goal=goal, value=baseline_value, direction=direction),
        optimized_value=optimized_value,
    )


class TestImproved:
    @pytest.mark.parametrize(
        ("direction", "baseline_value", "optimized_value", "improved"),
        [
            (BaselineDirection.MAXIMIZE, 20.0, 25.0, True),
            (BaselineDirection.MAXIMIZE, 20.0, 20.0, False),
            (BaselineDirection.MAXIMIZE, 20.0, 15.0, False),
            (BaselineDirection.MINIMIZE, 2000.0, 1800.0, True),
            (BaselineDirection.MINIMIZE, 2000.0, 2000.0, False),
            (BaselineDirection.MINIMIZE, 2000.0, 2200.0, False),
        ],
    )
    def test_reflects_a_strict_improvement_for_the_goal_direction(
        self,
        direction: BaselineDirection,
        baseline_value: float,
        optimized_value: float,
        improved: bool,
    ) -> None:
        outcome = _outcome(
            direction=direction,
            baseline_value=baseline_value,
            optimized_value=optimized_value,
        )

        assert outcome.improved is improved


class TestPlanSelection:
    def test_returns_the_optimized_plan_when_it_improves(self) -> None:
        outcome = _outcome(
            direction=BaselineDirection.MAXIMIZE, baseline_value=20.0, optimized_value=30.0
        )

        assert outcome.improved is True
        assert outcome.plan is _OPTIMIZED

    def test_returns_the_original_plan_on_a_tie(self) -> None:
        # A wash is not an improvement: keep what the user already had (safe no-op).
        outcome = _outcome(
            direction=BaselineDirection.MAXIMIZE, baseline_value=20.0, optimized_value=20.0
        )

        assert outcome.improved is False
        assert outcome.plan is _ORIGINAL

    def test_returns_the_original_plan_on_a_regression(self) -> None:
        outcome = _outcome(
            direction=BaselineDirection.MINIMIZE, baseline_value=2000.0, optimized_value=2100.0
        )

        assert outcome.improved is False
        assert outcome.plan is _ORIGINAL
