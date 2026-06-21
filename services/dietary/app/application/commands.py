"""Application command DTOs for the Dietary Planning use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.meal_plan import DietaryType, MacroTargets


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
