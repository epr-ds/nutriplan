"""HTTP request/response models for the AI API (camelCase, matching the OpenAPI contract).

These DTOs are the transport edge of the AI service. They are deliberately separate from the
LLM-facing value objects in :mod:`app.llm` and the scoring models in :mod:`app.scoring`: the wire
shape (defined in ``contracts/dietary.openapi.yaml``) can evolve independently of how the service
assembles prompts or scores candidates internally.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    """Base model that speaks camelCase on the wire but snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RecommendationContext(StrEnum):
    """What the caller wants recommendations for (drives prompt assembly in AIA-202)."""

    MEAL_PLAN = "meal_plan"
    SINGLE_MEAL = "single_meal"
    INGREDIENT_BASED = "ingredient_based"


class MealType(StrEnum):
    """Which meal a single-meal/ingredient recommendation targets."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class DietType(StrEnum):
    """Dietary pattern the caller follows."""

    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    KETO = "keto"
    PALEO = "paleo"
    MEDITERRANEAN = "mediterranean"


class DietaryTypeTag(StrEnum):
    """Dietary tags a recipe can satisfy (narrower than :class:`DietType`)."""

    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    KETO = "keto"
    PALEO = "paleo"


class Language(StrEnum):
    """Languages the advisor supports (prompt framework is es/en — AIA-103)."""

    ES = "es"
    EN = "en"


class MacroTargetsSchema(_Camel):
    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    sugar_grams: int | None = None


class DietaryPreferencesSchema(_Camel):
    diet_type: DietType | None = None
    allergies: list[str] = Field(default_factory=list)
    daily_calorie_target: int | None = Field(default=None, ge=1200, le=5000)
    macro_targets: MacroTargetsSchema | None = None
    excluded_ingredients: list[str] = Field(default_factory=list)
    cuisine_preferences: list[str] = Field(default_factory=list)


class AIRecommendationRequest(_Camel):
    """The validated request envelope for ``POST /ai/recommendations``."""

    context: RecommendationContext
    dietary_preferences: DietaryPreferencesSchema | None = None
    available_ingredients: list[str] = Field(default_factory=list)
    meal_type: MealType | None = None
    calorie_target: int | None = None
    previous_meals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    language: Language = Language.ES


class IngredientResponse(_Camel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class NutritionalInfoSchema(_Camel):
    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


class RecipeResponse(_Camel):
    id: str
    name: str
    description: str | None = None
    ingredients: list[IngredientResponse] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    prep_time: int | None = None
    cook_time: int | None = None
    servings: int
    image_url: str | None = None
    nutritional_info: NutritionalInfoSchema | None = None
    dietary_types: list[DietaryTypeTag] = Field(default_factory=list)


class NutritionalAlignmentResponse(_Camel):
    """The contract's compact alignment projection (``score`` + human-readable ``details``).

    Distinct from the rich :class:`app.scoring.types.NutritionalAlignment`; AIA-204 projects the
    scorer's output onto this wire shape.
    """

    score: float | None = None
    details: str | None = None


class AIRecommendationResponse(_Camel):
    recommendations: list[RecipeResponse] = Field(default_factory=list)
    reasoning: str | None = None
    nutritional_alignment: NutritionalAlignmentResponse | None = None
