"""What the plan-optimization use case produces (AIA-402+).

An :class:`OptimizationOutcome` is the application-level result the ``/ai/optimize-plan`` route
projects onto the contract's ``MealPlanResponse``. It carries:

- ``original`` — the plan as loaded, returned unchanged when optimization doesn't help;
- ``optimized`` — the plan after AIA-403's goal-directed constrained edits;
- ``baseline`` — the :class:`~app.optimization.baseline.BaselineMetric` measured on ``original``;
- ``optimized_value`` — the same metric re-measured on ``optimized`` (supplied by the service,
  which owns the measurement orchestration so this stays a pure value object).

The AIA-404 measurable-improvement check lives here: ``improved`` asks the baseline whether
``optimized_value`` is a *strict* gain for the goal's direction, and ``plan`` — the plan to actually
return — is the optimized plan only when it improved, else the original (a safe no-op). This keeps
the guarantee at the response boundary, independent of the optimizer's internal logic. AIA-405 will
add draft metadata around this same outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.optimization.baseline import BaselineMetric
from app.optimization.plan import OptimizationPlan


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    """An optimize-plan result with an improve-or-no-op guarantee on the returned plan."""

    original: OptimizationPlan
    optimized: OptimizationPlan
    baseline: BaselineMetric
    optimized_value: float

    @property
    def improved(self) -> bool:
        """Whether ``optimized`` strictly beats the baseline for the goal's direction."""
        return self.baseline.improves_on(self.optimized_value)

    @property
    def plan(self) -> OptimizationPlan:
        """The plan to return: the optimized one only when it improved, else the original."""
        return self.optimized if self.improved else self.original
