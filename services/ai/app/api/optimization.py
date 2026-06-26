"""``POST /ai/optimize-plan`` — optimize a meal plan toward its goals.

The transport edge (Bearer auth, ``planId``/``goal`` validation, the caller-owned plan lookup, and
the ``MealPlanResponse`` envelope) arrives in AIA-401. The route maps its validated request onto an
:class:`~app.optimization.commands.OptimizePlanCommand`, loads the caller-owned plan via the
injected service (forwarding the Bearer token so ownership is enforced downstream), returns ``404``
when the plan is absent or not the caller's, and projects the result onto the wire shape. AIA-405
makes that projection a **draft**: the optimized plan is returned with ``status: draft`` (the loaded
original untouched), so the client reviews it before accepting. The diff metadata the draft also
carries is consumed by the mobile/gateway slices that own the accept flow.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BearerToken, PlanOptimizationServiceDep
from app.api.schemas import MealPlanResponse, OptimizePlanRequest
from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.draft import PlanDraft

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/optimize-plan", response_model=MealPlanResponse)
def optimize_plan(
    request: OptimizePlanRequest,
    token: BearerToken,
    service: PlanOptimizationServiceDep,
) -> MealPlanResponse:
    """Optimize the caller's plan into a reviewable draft, or ``404`` if absent/not theirs."""
    outcome = service.optimize(_to_command(request), token=token)
    if outcome is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meal plan not found")
    draft = PlanDraft.from_outcome(outcome)
    return MealPlanResponse.from_plan(draft.plan)


def _to_command(request: OptimizePlanRequest) -> OptimizePlanCommand:
    """Translate the HTTP request into the application command the service consumes."""
    return OptimizePlanCommand(
        plan_id=str(request.plan_id),
        goal=OptimizationGoal(request.goal.value) if request.goal is not None else None,
    )
