"""The plan-optimization application service (AIA-401).

The service behind ``POST /ai/optimize-plan``. AIA-401 establishes the seam: it loads the
caller-owned plan through the :class:`~app.optimization.gateway.PlanGateway` port (forwarding the
Bearer token so ownership is enforced when the plan is fetched) and returns it unchanged — a missing
or not-owned plan surfaces as ``None``, which the route maps to ``404``.

Real optimization fills this seam without changing the route: AIA-402 computes baseline metrics over
the loaded plan, AIA-403 applies goal-driven constrained edits (respecting the AIA-501 guardrails),
AIA-404 re-scores the result against the baseline (improve-or-no-op), and AIA-405 returns the change
as a draft, leaving the original untouched.
"""

from __future__ import annotations

from app.optimization.commands import OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway, PlanGateway
from app.optimization.plan import OptimizationPlan


class PlanOptimizationService:
    """Load a caller-owned plan and (eventually) optimize it toward the requested goal."""

    def __init__(self, gateway: PlanGateway) -> None:
        self._gateway = gateway

    def optimize(self, command: OptimizePlanCommand, *, token: str) -> OptimizationPlan | None:
        """Return the optimized plan, or ``None`` when it is absent or not the caller's.

        For AIA-401 the "optimized" plan is the loaded plan unchanged; the optimization steps
        land in AIA-402-405 behind this same method signature.
        """
        return self._gateway.get_plan(command.plan_id, token=token)


def build_plan_optimization_service(
    gateway: PlanGateway | None = None,
) -> PlanOptimizationService:
    """Wire the service from configuration.

    Defaults to an empty in-memory gateway: until the real dietary-service adapter lands (AIA-402),
    production loads no plans, so every optimization honestly returns ``404`` rather than
    fabricating a result. Tests inject a seeded gateway (or override the whole service).
    """
    return PlanOptimizationService(gateway=gateway or InMemoryPlanGateway())
