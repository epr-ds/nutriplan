"""Application inputs for the recommendation use case (AIA-202).

These are the vocabulary and command DTO the recommendation prompt assembler consumes. They live
in the application layer (not the API layer) so the assembler never imports HTTP/pydantic concerns:
the ``/ai/recommendations`` route maps its validated request onto a :class:`RecommendationCommand`
in AIA-203, mirroring how the Dietary service translates requests into application commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecommendationContext(StrEnum):
    """What the caller wants recommendations for (selects the prompt template)."""

    MEAL_PLAN = "meal_plan"
    SINGLE_MEAL = "single_meal"
    INGREDIENT_BASED = "ingredient_based"


class MealType(StrEnum):
    """Which meal a single-meal / ingredient-based recommendation targets."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass(frozen=True, slots=True)
class MacroTargets:
    """Optional per-macro gram targets; ``None`` means the macro is untargeted."""

    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    sugar_grams: int | None = None

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (self.protein_grams, self.carbs_grams, self.fat_grams, self.sugar_grams)
        )


@dataclass(frozen=True, slots=True)
class RecommendationCommand:
    """Everything the assembler needs to build a preference-aware prompt.

    Collections are tuples so the command stays hashable and immutable (matching the Dietary
    service's frozen query DTOs). All dietary-profile fields are optional; the assembler fills
    absent ones with neutral, localized text so the prompt never carries an empty constraint.
    """

    context: RecommendationContext
    diet_type: str | None = None
    allergies: tuple[str, ...] = ()
    excluded_ingredients: tuple[str, ...] = ()
    cuisine_preferences: tuple[str, ...] = ()
    daily_calorie_target: int | None = None
    macro_targets: MacroTargets | None = None
    available_ingredients: tuple[str, ...] = ()
    meal_type: MealType | None = None
    calorie_target: int | None = None
    previous_meals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    count: int = 3

    def effective_calories(self) -> int | None:
        """The most specific energy target: a per-meal target if given, else the daily one."""
        return self.calorie_target or self.daily_calorie_target
