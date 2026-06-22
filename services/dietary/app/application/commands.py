"""Application command DTOs for the Dietary Planning use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.meal_plan import DietaryType, MacroTargets, MealPlanStatus, MealType


@dataclass(frozen=True)
class CreateMealPlanCommand:
    """Inputs for the *create meal plan* use case (DPL-102).

    ``user_id`` is supplied by the interface layer from the authenticated principal — it is never
    accepted from the request body, which keeps new plans scoped to the caller.
    """

    user_id: str
    name: str
    start_date: date
    end_date: date
    daily_calorie_target: int
    macro_targets: MacroTargets | None = None
    dietary_type: DietaryType | None = None


@dataclass(frozen=True)
class ListMealPlansQuery:
    """Inputs for the *list meal plans* use case (DPL-103).

    ``user_id`` comes from the authenticated principal, so results are always owner-scoped.
    ``page`` is 1-based; the service translates it to a repository ``skip`` offset.
    """

    user_id: str
    status: MealPlanStatus | None = None
    page: int = 1
    limit: int = 20


@dataclass(frozen=True)
class ChangeMealPlanStatusCommand:
    """Inputs for the *change meal-plan status* use case (DPL-106).

    ``user_id`` is taken from the authenticated principal so a caller can only transition their own
    plans. ``target_status`` is the lifecycle state to move to; the aggregate enforces which moves
    are legal.
    """

    user_id: str
    plan_id: str
    target_status: MealPlanStatus


@dataclass(frozen=True)
class AddMealToPlanCommand:
    """Inputs for the *add meal to plan* use case (DPL-105).

    ``user_id`` comes from the authenticated principal so a caller can only modify their own plans.
    ``recipe_id`` is validated against the recipe catalog by the application service.
    """

    user_id: str
    plan_id: str
    meal_type: MealType
    recipe_id: str
    servings: float
