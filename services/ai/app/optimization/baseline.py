"""Baseline metrics for plan optimization (AIA-402).

"I measure a plan before optimizing." Each :class:`~app.optimization.commands.OptimizationGoal`
maps to a single scalar derived from the plan's nutritional summary (the P2 totals/averages) plus a
:class:`BaselineDirection` saying which way is "better". :func:`measure_metric` is pure and
deterministic, so AIA-404 re-runs it on the optimized plan and asks the captured
:class:`BaselineMetric` whether it improved — returning the original on a tie or regression.

Metric per goal (all read the *daily average*, so multi-day plans compare against daily targets):
- ``increase_protein`` -> average protein grams (maximize).
- ``reduce_calories`` -> average calories (minimize).
- ``increase_satisfaction`` -> protein per 1000 kcal, a satiety proxy (maximize).
- ``balance_macros`` -> the AIA-106 nutrition-alignment score of the average vs the plan's targets,
  0-1 (maximize).

An ``None``/unknown input degrades the metric to ``0.0`` (a plan we cannot measure cannot be shown
to have improved), mirroring the scorer's "unknown is a miss" convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.optimization.commands import OptimizationGoal
from app.optimization.plan import NutritionTargets, OptimizationPlan, PlanNutrition
from app.scoring import NutrientProfile, NutrientTargets, ScoringCandidate, score_alignment


class BaselineDirection(StrEnum):
    """Which direction counts as an improvement for a goal's metric."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


_DIRECTIONS: dict[OptimizationGoal, BaselineDirection] = {
    OptimizationGoal.BALANCE_MACROS: BaselineDirection.MAXIMIZE,
    OptimizationGoal.INCREASE_PROTEIN: BaselineDirection.MAXIMIZE,
    OptimizationGoal.REDUCE_CALORIES: BaselineDirection.MINIMIZE,
    OptimizationGoal.INCREASE_SATISFACTION: BaselineDirection.MAXIMIZE,
}


@dataclass(frozen=True, slots=True)
class BaselineMetric:
    """The measured starting point for a goal, retained for the AIA-404 improvement check."""

    goal: OptimizationGoal
    value: float
    direction: BaselineDirection

    def improves_on(self, candidate: float) -> bool:
        """Whether ``candidate`` strictly improves on this baseline (ties do not count)."""
        if self.direction is BaselineDirection.MAXIMIZE:
            return candidate > self.value
        return candidate < self.value


def measure_metric(plan: OptimizationPlan, goal: OptimizationGoal) -> float:
    """Measure ``plan`` against ``goal`` from its nutritional summary (``0.0`` if unmeasurable)."""
    summary = plan.nutritional_summary
    if summary is None:
        return 0.0
    average = summary.daily_average
    if goal is OptimizationGoal.INCREASE_PROTEIN:
        return float(average.protein or 0.0)
    if goal is OptimizationGoal.REDUCE_CALORIES:
        return float(average.calories or 0.0)
    if goal is OptimizationGoal.INCREASE_SATISFACTION:
        return _protein_density(average)
    return _macro_balance(average, summary.targets)


def baseline_for(plan: OptimizationPlan, goal: OptimizationGoal) -> BaselineMetric:
    """Measure the plan and tag the metric with the goal and its improvement direction."""
    return BaselineMetric(goal=goal, value=measure_metric(plan, goal), direction=_DIRECTIONS[goal])


def metric_direction(goal: OptimizationGoal) -> BaselineDirection:
    """Which direction improves ``goal``'s metric — so the AIA-403 optimizer can climb it."""
    return _DIRECTIONS[goal]


def _protein_density(average: PlanNutrition) -> float:
    """Grams of protein per 1000 kcal — a deterministic satiety proxy (``0.0`` when undefined)."""
    calories = average.calories or 0
    protein = average.protein or 0.0
    if calories <= 0 or protein <= 0:
        return 0.0
    return protein / calories * 1000.0


def _macro_balance(average: PlanNutrition, targets: NutritionTargets) -> float:
    """The AIA-106 nutrition-alignment score of the daily average against the plan's targets."""
    candidate = ScoringCandidate(
        nutrition=NutrientProfile(
            calories=average.calories,
            protein=average.protein,
            carbs=average.carbs,
            fat=average.fat,
            sugar=average.sugar,
        )
    )
    nutrient_targets = NutrientTargets(
        calories=targets.calories,
        protein=targets.protein,
        carbs=targets.carbs,
        fat=targets.fat,
        sugar=targets.sugar,
    )
    return score_alignment(candidate, nutrient_targets).nutrition_score
