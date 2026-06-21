"""MealPlans API router (DPL-102/103)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, MealPlanServiceDep
from app.api.schemas import (
    CreateMealPlanRequest,
    MealPlanResponse,
    MealPlanStatusFilter,
    MealPlanSummaryResponse,
)
from app.application.commands import CreateMealPlanCommand, ListMealPlansQuery
from app.domain.meal_plan import MacroTargets, MealPlanStatus

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


@router.get(
    "",
    response_model=list[MealPlanSummaryResponse],
    summary="List the current user's meal plans",
)
def list_meal_plans(
    principal: CurrentPrincipal,
    service: MealPlanServiceDep,
    status_filter: Annotated[MealPlanStatusFilter | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[MealPlanSummaryResponse]:
    """List the caller's meal plans, with optional status filter + pagination (DPL-103)."""
    query = ListMealPlansQuery(
        user_id=principal.user_id,
        status=MealPlanStatus(status_filter.value) if status_filter is not None else None,
        page=page,
        limit=limit,
    )
    plans = service.list_meal_plans(query)
    return [MealPlanSummaryResponse.from_aggregate(p) for p in plans]
