"""What the plan-optimization use case produces (AIA-402+).

An :class:`OptimizationOutcome` is the application-level result the ``/ai/optimize-plan`` route
projects onto the contract's ``MealPlanResponse``. It carries:

- ``original`` — the plan as loaded, so AIA-404 can fall back to it (improve-or-no-op);
- ``optimized`` — the plan after AIA-403's goal-directed constrained edits;
- ``baseline`` — the :class:`~app.optimization.baseline.BaselineMetric` measured on ``original``,
  retained so AIA-404 can re-measure ``optimized`` and confirm a real improvement.

``plan`` is the plan to actually return. For AIA-403 that is the ``optimized`` plan; AIA-404 will
refine ``plan`` into the improve-or-no-op decision (``optimized`` only when it beats the baseline,
else ``original``) without changing the route.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.optimization.baseline import BaselineMetric
from app.optimization.plan import OptimizationPlan


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    """The result of an optimize-plan request: the loaded + optimized plans and the baseline."""

    original: OptimizationPlan
    optimized: OptimizationPlan
    baseline: BaselineMetric

    @property
    def plan(self) -> OptimizationPlan:
        """The plan to return — the optimized one (AIA-404 makes this improve-or-no-op)."""
        return self.optimized
