"""The optimized-plan draft and its diff metadata (AIA-405).

Optimization never overwrites the user's plan. The use case returns a :class:`PlanDraft` — a
proposal the user reviews before committing: the optimized plan re-statused to ``draft`` (the
loaded original is left untouched) plus a :class:`PlanDiff` summarizing what changed, so the UI can
render a before/after and a one-line "why".

The draft is derived from the AIA-404 :class:`~app.optimization.result.OptimizationOutcome`, so it
inherits the improve-or-no-op guarantee: when the optimization actually beat the baseline the draft
proposes the optimized plan and the diff lists the serving edits; when it did not (a no-op), the
draft proposes the original unchanged and the diff is empty. Accepting a draft is handled
separately in :mod:`app.optimization.acceptance`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.optimization.baseline import BaselineDirection, BaselineMetric
from app.optimization.commands import OptimizationGoal
from app.optimization.plan import OptimizationPlan
from app.optimization.result import OptimizationOutcome

DRAFT_STATUS = "draft"


@dataclass(frozen=True, slots=True)
class MealServingChange:
    """How one meal's servings move from the original plan to the proposal."""

    meal_id: str
    meal_type: str
    previous_servings: float
    new_servings: float

    @property
    def delta(self) -> float:
        """The signed change in servings (positive when the proposal serves more)."""
        return self.new_servings - self.previous_servings


@dataclass(frozen=True, slots=True)
class PlanDiff:
    """What an optimization changed: the goal metric's movement and the per-meal serving edits."""

    goal: OptimizationGoal
    baseline_value: float
    optimized_value: float
    improvement: float
    improved: bool
    meal_changes: tuple[MealServingChange, ...]

    @property
    def has_changes(self) -> bool:
        """Whether any meal's servings changed."""
        return bool(self.meal_changes)

    @classmethod
    def between(
        cls,
        original: OptimizationPlan,
        proposed: OptimizationPlan,
        *,
        baseline: BaselineMetric,
        optimized_value: float,
    ) -> PlanDiff:
        """Diff ``proposed`` against ``original`` for the baseline's goal.

        ``improvement`` is the signed gain in the goal's *favorable* direction, so it is positive
        for a real improvement whether the metric is maximized (e.g. protein) or minimized (e.g.
        calories); ``improved`` reuses the baseline's strict comparison so a tie never counts.
        """
        if baseline.direction is BaselineDirection.MAXIMIZE:
            improvement = optimized_value - baseline.value
        else:
            improvement = baseline.value - optimized_value
        return cls(
            goal=baseline.goal,
            baseline_value=baseline.value,
            optimized_value=optimized_value,
            improvement=improvement,
            improved=baseline.improves_on(optimized_value),
            meal_changes=_meal_changes(original, proposed),
        )


@dataclass(frozen=True, slots=True)
class PlanDraft:
    """A reviewable optimization proposal: the original, the proposed plan, and their diff."""

    original: OptimizationPlan
    proposed: OptimizationPlan
    diff: PlanDiff

    @property
    def improved(self) -> bool:
        """Whether the proposal is a real improvement (vs an unchanged no-op)."""
        return self.diff.improved

    @property
    def plan(self) -> OptimizationPlan:
        """The plan the route returns: the draft proposal (the original when nothing improved)."""
        return self.proposed

    @classmethod
    def from_outcome(cls, outcome: OptimizationOutcome) -> PlanDraft:
        """Build the draft from an :class:`OptimizationOutcome` (AIA-404's improve-or-no-op)."""
        if outcome.improved:
            basis = outcome.optimized
            metric_value = outcome.optimized_value
            proposed = replace(basis, status=DRAFT_STATUS)
        else:
            # No improvement: there is nothing to draft — propose the original, untouched.
            basis = outcome.original
            metric_value = outcome.baseline.value
            proposed = outcome.original
        diff = PlanDiff.between(
            outcome.original, basis, baseline=outcome.baseline, optimized_value=metric_value
        )
        return cls(original=outcome.original, proposed=proposed, diff=diff)


def _meal_changes(
    original: OptimizationPlan, proposed: OptimizationPlan
) -> tuple[MealServingChange, ...]:
    """Per-meal serving changes, paired by meal id (optimization only adjusts existing servings)."""
    proposed_by_id = {meal.id: meal for meal in proposed.meals}
    changes = [
        MealServingChange(
            meal_id=meal.id,
            meal_type=meal.meal_type,
            previous_servings=meal.servings,
            new_servings=other.servings,
        )
        for meal in original.meals
        if (other := proposed_by_id.get(meal.id)) is not None and other.servings != meal.servings
    ]
    return tuple(changes)
