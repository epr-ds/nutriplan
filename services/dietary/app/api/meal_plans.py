"""MealPlans API router (DPL-102/103)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, MealPlanServiceDep, MealServiceDep
from app.api.schemas import (
    AddMealRequest,
    CreateMealPlanRequest,
    MealPlanResponse,
    MealPlanStatusFilter,
    MealPlanSummaryResponse,
    MealResponse,
    UpdateMealPlanStatusRequest,
)
from app.application.commands import (
    AddMealToPlanCommand,
    ChangeMealPlanStatusCommand,
    CreateMealPlanCommand,
    ListMealPlansQuery,
)
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


@router.get(
    "/{plan_id}",
    response_model=MealPlanResponse,
    summary="Get a specific meal plan",
)
def get_meal_plan(
    plan_id: str,
    principal: CurrentPrincipal,
    service: MealPlanServiceDep,
) -> MealPlanResponse:
    """Return the caller's meal plan by id with full detail, or 404 if missing/!owned (DPL-104)."""
    plan = service.get_meal_plan(principal.user_id, plan_id)
    return MealPlanResponse.from_aggregate(plan)


@router.patch(
    "/{plan_id}",
    response_model=MealPlanResponse,
    summary="Change a meal plan's lifecycle status",
)
def update_meal_plan_status(
    plan_id: str,
    body: UpdateMealPlanStatusRequest,
    principal: CurrentPrincipal,
    service: MealPlanServiceDep,
) -> MealPlanResponse:
    """Transition the caller's plan through its lifecycle (DPL-106).

    Returns the updated plan; an illegal transition is ``409``, activating a plan with no meals is
    ``422``, and a missing or not-owned plan is ``404``.
    """
    command = ChangeMealPlanStatusCommand(
        user_id=principal.user_id,
        plan_id=plan_id,
        target_status=MealPlanStatus(body.status.value),
    )
    plan = service.change_meal_plan_status(command)
    return MealPlanResponse.from_aggregate(plan)


@router.post(
    "/{plan_id}/meals",
    response_model=MealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a meal to a meal plan",
)
def add_meal_to_plan(
    plan_id: str,
    body: AddMealRequest,
    principal: CurrentPrincipal,
    service: MealServiceDep,
) -> MealResponse:
    """Add a meal (a recipe reference + servings) to the caller's plan (DPL-105).

    Returns the created meal with its recipe; a missing or not-owned plan is ``404``, while an
    unknown recipe or non-positive ``servings`` is ``422``.
    """
    command = AddMealToPlanCommand(
        user_id=principal.user_id,
        plan_id=plan_id,
        meal_type=body.meal_type,
        recipe_id=body.recipe_id,
        servings=body.servings,
    )
    meal, recipe = service.add_meal_to_plan(command)
    return MealResponse.from_meal(meal, recipe)
