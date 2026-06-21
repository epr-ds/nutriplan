"""HTTP request/response models for the MealPlans API (camelCase, matching the OpenAPI contract).

These DTOs are deliberately separate from the domain aggregate: the wire shape can evolve
independently of the persistence/domain model, and the response is a *projection* of the aggregate
(it never exposes ``userId`` or internal timestamps).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.meal_plan import DietaryType, MealPlan, MealPlanStatus, MealType


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MacroTargetsSchema(_Camel):
    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    sugar_grams: int | None = None


class NutritionalInfoSchema(_Camel):
    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class CreateMealPlanRequest(_Camel):
    """Body of ``POST /meal-plans`` (CreateMealPlanRequest)."""

    name: str = Field(min_length=1)
    start_date: date
    end_date: date
    daily_calorie_target: int
    macro_targets: MacroTargetsSchema | None = None
    dietary_type: DietaryType | None = None


class MealResponse(_Camel):
    id: str
    meal_type: MealType
    servings: float
    nutritional_info: NutritionalInfoSchema | None = None


class MealPlanResponse(_Camel):
    """``MealPlanResponse`` — the caller-facing projection of a meal plan."""

    id: str
    name: str
    start_date: date
    end_date: date
    daily_calorie_target: int
    status: MealPlanStatus
    meals: list[MealResponse] = Field(default_factory=list)

    @classmethod
    def from_aggregate(cls, plan: MealPlan) -> MealPlanResponse:
        return cls(
            id=plan.id,
            name=plan.name,
            start_date=plan.start_date,
            end_date=plan.end_date,
            daily_calorie_target=plan.daily_calorie_target,
            status=MealPlanStatus(plan.status),
            meals=[
                MealResponse(
                    id=meal.id,
                    meal_type=MealType(meal.meal_type),
                    servings=meal.servings,
                    nutritional_info=(
                        NutritionalInfoSchema(**meal.nutritional_info.model_dump())
                        if meal.nutritional_info is not None
                        else None
                    ),
                )
                for meal in plan.meals
            ],
        )
