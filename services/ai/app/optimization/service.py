"""The plan-optimization application service (AIA-401, AIA-402).

The service behind ``POST /ai/optimize-plan``. AIA-401 established the seam: it loads the
caller-owned plan through the :class:`~app.optimization.gateway.PlanGateway` port (forwarding the
Bearer token so ownership is enforced when the plan is fetched) — a missing or not-owned plan
surfaces as ``None``, which the route maps to ``404``. AIA-402 then *measures* the loaded plan: it
resolves the effective goal (defaulting to ``balance_macros`` when the caller omits one) and
computes a :class:`~app.optimization.baseline.BaselineMetric`, returning both in an
:class:`~app.optimization.result.OptimizationOutcome`.

Real optimization fills the rest of the seam without changing the route: AIA-403 applies goal-driven
constrained edits (respecting the AIA-501 guardrails), AIA-404 re-scores the result against the
baseline (improve-or-no-op), and AIA-405 returns the change as a draft, leaving the original
untouched.
"""

from __future__ import annotations

from app.optimization.baseline import baseline_for
from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway, PlanGateway
from app.optimization.result import OptimizationOutcome

_DEFAULT_GOAL = OptimizationGoal.BALANCE_MACROS


class PlanOptimizationService:
    """Load a caller-owned plan, measure it, and (eventually) optimize it toward the goal."""

    def __init__(self, gateway: PlanGateway) -> None:
        self._gateway = gateway

    def optimize(self, command: OptimizePlanCommand, *, token: str) -> OptimizationOutcome | None:
        """Return the measured outcome, or ``None`` when the plan is absent or not the caller's.

        For AIA-401/402 the outcome's plan is the loaded plan unchanged, alongside the baseline
        measured for the (effective) goal; the optimization steps land in AIA-403-405 behind this
        same method signature.
        """
        plan = self._gateway.get_plan(command.plan_id, token=token)
        if plan is None:
            return None
        goal = command.goal or _DEFAULT_GOAL
        return OptimizationOutcome(plan=plan, baseline=baseline_for(plan, goal))


def build_plan_optimization_service(
    gateway: PlanGateway | None = None,
) -> PlanOptimizationService:
    """Wire the service from configuration.

    Defaults to an empty in-memory gateway: until the real dietary-service adapter lands (AIA-402),
    production loads no plans, so every optimization honestly returns ``404`` rather than
    fabricating a result. Tests inject a seeded gateway (or override the whole service).
    """
    return PlanOptimizationService(gateway=gateway or InMemoryPlanGateway())
