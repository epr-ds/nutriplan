"""What the plan-optimization use case produces (AIA-402+).

An :class:`OptimizationOutcome` is the application-level result the ``/ai/optimize-plan`` route
projects onto the contract's ``MealPlanResponse``. AIA-402 carries the (loaded) plan plus the
:class:`~app.optimization.baseline.BaselineMetric` measured before optimizing — retained so the
AIA-404 improvement check can compare the optimized plan against it. AIA-403 will swap ``plan`` for
the edited plan, and AIA-404/405 will grow the outcome (the measurable-improvement verdict, the
draft framing) without changing the route.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.optimization.baseline import BaselineMetric
from app.optimization.plan import OptimizationPlan


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    """The result of an optimize-plan request: the plan to return plus its measured baseline."""

    plan: OptimizationPlan
    baseline: BaselineMetric
