"""MealPlans API router (DPL-102)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, MealPlanServiceDep
from app.api.schemas import CreateMealPlanRequest, MealPlanResponse
from app.application.commands import CreateMealPlanCommand
from app.domain.meal_plan import MacroTargets

router = APIRouter(prefix="/meal-plans", tags=["MealPlans"])


@router.post(
    "",
    response_model=MealPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new meal plan",
)
def create_meal_plan(
    body: CreateMealPlanRequest,
    principal: CurrentPrincipal,
    service: MealPlanServiceDep,
) -> MealPlanResponse:
    """Create a draft meal plan owned by the authenticated caller (DPL-102)."""
    command = CreateMealPlanCommand(
        user_id=principal.user_id,
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
        daily_calorie_target=body.daily_calorie_target,
        macro_targets=(
            MacroTargets(**body.macro_targets.model_dump()) if body.macro_targets else None
        ),
        dietary_type=body.dietary_type,
    )
    plan = service.create_meal_plan(command)
    return MealPlanResponse.from_aggregate(plan)
