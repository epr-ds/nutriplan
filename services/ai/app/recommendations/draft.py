"""The schema the model must fill when recommending recipes (AIA-203).

These Pydantic models are the structured-output contract for the recommendation call: the AIA-104
loop turns ``RecommendationDraft`` into the provider's response-format constraint *and* validates
the reply against it, so a recommendation that reaches the mapper is guaranteed to carry a name,
ingredients, steps, servings, and nutrition. Optional fields (description, prep/cook time, per-macro
detail) may be omitted by the model without failing validation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngredientDraft(BaseModel):
    """One ingredient line the model proposes for a recipe."""

    name: str
    quantity: float | None = None
    unit: str | None = None


class NutritionDraft(BaseModel):
    """Per-serving nutrition the model estimates for a recipe."""

    calories: int
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


class RecipeDraft(BaseModel):
    """A single recommended recipe as proposed by the model."""

    name: str
    description: str | None = None
    ingredients: list[IngredientDraft]
    instructions: list[str]
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int
    nutrition: NutritionDraft
    dietary_types: list[str] = Field(default_factory=list)


class RecommendationDraft(BaseModel):
    """The model's full reply: the recipes it recommends, plus why they fit."""

    recipes: list[RecipeDraft] = Field(default_factory=list)
    reasoning: str | None = Field(
        default=None,
        description=(
            "A short explanation, in the request's language, of why these recipes fit -- "
            "referencing the user's calorie/macro targets and dietary preferences."
        ),
    )
