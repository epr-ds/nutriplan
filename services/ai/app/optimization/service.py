"""The plan-optimization application service (AIA-401, AIA-402, AIA-403, AIA-404).

The service behind ``POST /ai/optimize-plan``. AIA-401 established the seam: it loads the
caller-owned plan through the :class:`~app.optimization.gateway.PlanGateway` port (forwarding the
Bearer token so ownership is enforced when the plan is fetched) — a missing or not-owned plan
surfaces as ``None``, which the route maps to ``404``. AIA-402 then *measures* the loaded plan: it
resolves the effective goal (defaulting to ``balance_macros`` when the caller omits one) and
computes a :class:`~app.optimization.baseline.BaselineMetric`. AIA-403 *edits* it: a
:class:`~app.optimization.optimizer.PlanOptimizer` applies goal-directed, allergen-safe serving
adjustments. AIA-404 *re-scores* the result: the service measures the optimized plan for the same
goal and hands both metrics to an :class:`~app.optimization.result.OptimizationOutcome`, which
returns the optimized plan only when it strictly beat the baseline, else the original unchanged
(a safe no-op).

The remaining step slots in behind this method without changing the route: AIA-405 returns the
change as a draft, leaving the original untouched.
"""

from __future__ import annotations

from app.optimization.baseline import baseline_for, measure_metric
from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway, PlanGateway
from app.optimization.optimizer import PlanOptimizer
from app.optimization.result import OptimizationOutcome

_DEFAULT_GOAL = OptimizationGoal.BALANCE_MACROS


class PlanOptimizationService:
    """Load a caller-owned plan, measure it, and optimize it toward the goal."""

    def __init__(self, gateway: PlanGateway, optimizer: PlanOptimizer | None = None) -> None:
        self._gateway = gateway
        self._optimizer = optimizer or PlanOptimizer()

    def optimize(self, command: OptimizePlanCommand, *, token: str) -> OptimizationOutcome | None:
        """Return the optimized outcome, or ``None`` when the plan is absent or not the caller's.

        The plan is loaded, measured for the (effective) goal, optimized with bounded, allergen-safe
        serving edits, then the optimized plan is **re-measured** for the same goal. Both metrics
        ride along in the outcome, which decides whether the optimization actually improved things
        (AIA-404): the route receives the optimized plan only when it strictly beat the baseline,
        else the original unchanged.
        """
        plan = self._gateway.get_plan(command.plan_id, token=token)
        if plan is None:
            return None
        goal = command.goal or _DEFAULT_GOAL
        baseline = baseline_for(plan, goal)
        optimized = self._optimizer.optimize(plan, goal)
        optimized_value = measure_metric(optimized, goal)
        return OptimizationOutcome(
            original=plan,
            optimized=optimized,
            baseline=baseline,
            optimized_value=optimized_value,
        )


def build_plan_optimization_service(
    gateway: PlanGateway | None = None,
    *,
    optimizer: PlanOptimizer | None = None,
) -> PlanOptimizationService:
    """Wire the service from configuration.

    Defaults to an empty in-memory gateway: until the real dietary-service adapter lands, production
    loads no plans, so every optimization honestly returns ``404`` rather than fabricating a result.
    Tests inject a seeded gateway (or override the whole service).
    """
    return PlanOptimizationService(gateway=gateway or InMemoryPlanGateway(), optimizer=optimizer)
