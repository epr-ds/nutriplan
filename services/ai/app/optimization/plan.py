"""The plan the optimizer works on (AIA-401).

These are the application-level value objects for a meal plan as loaded from the dietary service
(via the :class:`~app.optimization.gateway.PlanGateway` port). They are free of any HTTP/pydantic
concern; the route projects an :class:`OptimizationPlan` onto the contract's ``MealPlanResponse``.
AIA-401 loads and echoes the plan; AIA-402 computes baseline metrics over these same objects.

A ``None`` nutrient means "unknown / not measured", kept distinct from a measured zero (matching the
dietary nutrition model). Recipes are referenced by id only — plan reads do not expand them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class PlanNutrition:
    """A bundle of nutrient values for a meal or a plan total/average."""

    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


@dataclass(frozen=True, slots=True)
class NutritionTargets:
    """A plan's nutrition goals: its daily calorie target plus optional macro gram targets."""

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


@dataclass(frozen=True, slots=True)
class PlanNutritionSummary:
    """The plan's total and daily-average nutrition versus its targets (dietary DPL-302)."""

    total: PlanNutrition
    daily_average: PlanNutrition
    targets: NutritionTargets


@dataclass(frozen=True, slots=True)
class OptimizationMeal:
    """One planned meal: its slot, servings, and (optional) computed nutrition."""

    id: str
    meal_type: str
    servings: float
    nutrition: PlanNutrition | None = None


@dataclass(frozen=True, slots=True)
class OptimizationPlan:
    """A meal plan loaded for optimization, mirroring the dietary ``MealPlanResponse`` shape."""

    id: str
    name: str
    start_date: date
    end_date: date
    daily_calorie_target: int
    status: str
    meals: tuple[OptimizationMeal, ...] = field(default_factory=tuple)
    nutritional_summary: PlanNutritionSummary | None = None

    @classmethod
    def with_meals(
        cls,
        *,
        id: str,
        name: str,
        start_date: date,
        end_date: date,
        daily_calorie_target: int,
        status: str,
        meals: Iterable[OptimizationMeal] = (),
        nutritional_summary: PlanNutritionSummary | None = None,
    ) -> OptimizationPlan:
        """Build a plan from any iterable of meals (normalized to a tuple for immutability)."""
        return cls(
            id=id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            daily_calorie_target=daily_calorie_target,
            status=status,
            meals=tuple(meals),
            nutritional_summary=nutritional_summary,
        )
