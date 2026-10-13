"""Goal-directed constrained optimization of a meal plan (AIA-403).

The optimizer improves a loaded plan toward its goal using the one edit that is safe by
construction: adjusting the *servings* of the recipes already in the plan. It never adds, removes,
or substitutes a recipe, so it cannot introduce an allergen or an invalid recipe — it only dials the
existing, already-valid meals up or down within a bounded :class:`ServingPolicy` ("valid servings").

It is a deterministic greedy hill-climb over those serving steps: each round it generates every
legal single-step adjustment, scores the result with the AIA-402 ``measure_metric`` for the goal,
and keeps the step that most improves it; it stops when no step improves the metric (or the
iteration cap is hit). Reusing ``measure_metric`` guarantees the optimizer and AIA-404's
improvement check agree on what "better" means.

Allergies/exclusions (AIA-501) are honored as a hard guard: a meal containing an excluded ingredient
is *locked from increase* — the optimizer may keep or shrink it but never amplifies a meal the
caller wants to avoid. (AIA-501 adds the prompt-side constraints + violation logging for synthesized
recipes; serving edits need only this structural guard, since they introduce no new ingredient.)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

from app.optimization.baseline import BaselineDirection, measure_metric, metric_direction
from app.optimization.commands import OptimizationGoal
from app.optimization.plan import (
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)


@dataclass(frozen=True, slots=True)
class ServingPolicy:
    """The bounds that keep a serving edit valid: a min/max and the step it moves in."""

    minimum: float = 0.5
    maximum: float = 4.0
    step: float = 0.5
    max_iterations: int = 64


_DEFAULT_POLICY = ServingPolicy()


class PlanOptimizer:
    """Hill-climb a plan toward its goal via bounded, allergen-safe serving adjustments."""

    def __init__(self, policy: ServingPolicy | None = None) -> None:
        self._policy = policy or _DEFAULT_POLICY

    def optimize(self, plan: OptimizationPlan, goal: OptimizationGoal) -> OptimizationPlan:
        """Return a plan edited toward ``goal``, or the plan unchanged when no edit helps it."""
        if plan.nutritional_summary is None:
            return plan
        direction = metric_direction(goal)
        excluded = plan.constraints.excluded()
        current = plan
        current_metric = measure_metric(current, goal)
        for _ in range(self._policy.max_iterations):
            best_plan: OptimizationPlan | None = None
            best_metric = current_metric
            for candidate in self._candidates(current, excluded):
                metric = measure_metric(candidate, goal)
                if _is_better(metric, best_metric, direction):
                    best_plan, best_metric = candidate, metric
            if best_plan is None:
                return current
            current, current_metric = best_plan, best_metric
        return current

    def _candidates(
        self, plan: OptimizationPlan, excluded: frozenset[str]
    ) -> Iterator[OptimizationPlan]:
        """Every legal one-step serving change of a single meal (deterministic order)."""
        for index, meal in enumerate(plan.meals):
            if meal.nutrition is None or meal.servings <= 0:
                continue
            locked = self._is_excluded(meal, excluded)
            for delta in (self._policy.step, -self._policy.step):
                if delta > 0 and locked:
                    continue
                new_servings = round(meal.servings + delta, 4)
                if new_servings < self._policy.minimum or new_servings > self._policy.maximum:
                    continue
                yield self._adjust(plan, index, meal, new_servings)

    def _adjust(
        self,
        plan: OptimizationPlan,
        index: int,
        meal: OptimizationMeal,
        new_servings: float,
    ) -> OptimizationPlan:
        """Rescale one meal to ``new_servings`` and patch the plan summary by the difference."""
        assert meal.nutrition is not None  # guaranteed by the caller
        factor = new_servings / meal.servings
        change = _scaled(meal.nutrition, factor - 1.0)
        meals = list(plan.meals)
        meals[index] = replace(
            meal, servings=new_servings, nutrition=_scaled(meal.nutrition, factor)
        )
        summary = plan.nutritional_summary
        assert summary is not None  # optimize() returns early when there is no summary
        per_day = _scaled(change, 1.0 / _plan_days(plan))
        patched = PlanNutritionSummary(
            total=_added(summary.total, change),
            daily_average=_added(summary.daily_average, per_day),
            targets=summary.targets,
        )
        return replace(plan, meals=tuple(meals), nutritional_summary=patched)

    @staticmethod
    def _is_excluded(meal: OptimizationMeal, excluded: frozenset[str]) -> bool:
        return any(ingredient.casefold() in excluded for ingredient in meal.ingredients)


def _is_better(candidate: float, reference: float, direction: BaselineDirection) -> bool:
    """Whether ``candidate`` strictly beats ``reference`` for the goal's direction."""
    if direction is BaselineDirection.MAXIMIZE:
        return candidate > reference
    return candidate < reference


def _plan_days(plan: OptimizationPlan) -> int:
    """The inclusive number of days the plan spans (at least one)."""
    return max((plan.end_date - plan.start_date).days + 1, 1)


def _scaled(nutrition: PlanNutrition, factor: float) -> PlanNutrition:
    """Scale every known nutrient by ``factor`` (calories stay integral; ``None`` stays unknown)."""
    return PlanNutrition(
        calories=round(nutrition.calories * factor) if nutrition.calories is not None else None,
        protein=nutrition.protein * factor if nutrition.protein is not None else None,
        carbs=nutrition.carbs * factor if nutrition.carbs is not None else None,
        fat=nutrition.fat * factor if nutrition.fat is not None else None,
        sugar=nutrition.sugar * factor if nutrition.sugar is not None else None,
    )


def _added(base: PlanNutrition, change: PlanNutrition) -> PlanNutrition:
    """Add ``change`` onto ``base`` per nutrient, leaving a value unknown if either side is."""
    return PlanNutrition(
        calories=_add_int(base.calories, change.calories),
        protein=_add(base.protein, change.protein),
        carbs=_add(base.carbs, change.carbs),
        fat=_add(base.fat, change.fat),
        sugar=_add(base.sugar, change.sugar),
    )


def _add(base: float | None, change: float | None) -> float | None:
    if base is None or change is None:
        return base
    return base + change


def _add_int(base: int | None, change: int | None) -> int | None:
    if base is None or change is None:
        return base
    return round(base + change)
