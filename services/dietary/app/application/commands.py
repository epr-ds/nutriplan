"""Application command DTOs for the Dietary Planning use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.meal_plan import DietaryType, MacroTargets, MealPlanStatus


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
