"""HTTP request/response models for the AI API (camelCase, matching the OpenAPI contract).

These DTOs are the transport edge of the AI service. They are deliberately separate from the
LLM-facing value objects in :mod:`app.llm` and the scoring models in :mod:`app.scoring`: the wire
shape (defined in ``contracts/dietary.openapi.yaml``) can evolve independently of how the service
assembles prompts or scores candidates internally.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    from app.analysis.result import MealAnalysis
    from app.optimization.plan import (
        OptimizationMeal,
        OptimizationPlan,
        PlanNutrition,
        PlanNutritionSummary,
    )
    from app.recommendations.alignment import RecommendationAlignment
    from app.recommendations.recipes import RecommendedRecipe


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


_DIETARY_TAG_VALUES = frozenset(tag.value for tag in DietaryTypeTag)


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
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


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

    @classmethod
    def from_recommended(cls, recipe: RecommendedRecipe) -> RecipeResponse:
        """Project an application :class:`RecommendedRecipe` onto the wire shape (AIA-203).

        Unknown dietary tags (e.g. a cuisine-style label the wire enum doesn't model) are dropped
        rather than rejected, so a synthesized recipe never fails to serialize.
        """
        return cls(
            id=recipe.id,
            name=recipe.name,
            description=recipe.description,
            ingredients=[
                IngredientResponse(name=item.name, quantity=item.quantity, unit=item.unit)
                for item in recipe.ingredients
            ],
            instructions=list(recipe.instructions),
            prep_time=recipe.prep_time_minutes,
            cook_time=recipe.cook_time_minutes,
            servings=recipe.servings,
            nutritional_info=NutritionalInfoSchema(
                calories=recipe.nutrition.calories,
                protein=recipe.nutrition.protein,
                carbs=recipe.nutrition.carbs,
                fat=recipe.nutrition.fat,
                sugar=recipe.nutrition.sugar,
            ),
            dietary_types=[
                DietaryTypeTag(value)
                for tag in recipe.dietary_types
                if (value := tag.strip().lower()) in _DIETARY_TAG_VALUES
            ],
        )


class NutritionalAlignmentResponse(_Camel):
    """The contract's compact alignment projection (``score`` + human-readable ``details``).

    Distinct from the rich :class:`app.scoring.types.NutritionalAlignment`; AIA-204 projects the
    aggregated :class:`app.recommendations.alignment.RecommendationAlignment` onto this wire shape,
    exposing ``score`` as a 0-100 percentage.
    """

    score: float | None = None
    details: str | None = None

    @classmethod
    def from_alignment(cls, alignment: RecommendationAlignment) -> NutritionalAlignmentResponse:
        """Project an aggregated :class:`RecommendationAlignment` onto the wire shape (AIA-204)."""
        return cls(score=alignment.percentage, details=alignment.details)


class AIRecommendationResponse(_Camel):
    recommendations: list[RecipeResponse] = Field(default_factory=list)
    reasoning: str | None = None
    nutritional_alignment: NutritionalAlignmentResponse | None = None
    disclaimer: str | None = None


class AnalyzeMealRequest(_Camel):
    """The validated request envelope for ``POST /ai/analyze-meal`` (AIA-301).

    ``description`` (free text) is required; structured ``ingredients`` are optional and reuse the
    ingredient wire shape, carrying optional per-ingredient nutrition hints.
    """

    description: str
    ingredients: list[IngredientResponse] = Field(default_factory=list)


class NutritionalAnalysisResponse(_Camel):
    """The contract's analysis projection: estimated nutrition, optional alignment, and warnings."""

    nutritional_info: NutritionalInfoSchema | None = None
    alignment: NutritionalAlignmentResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str | None = None

    @classmethod
    def from_analysis(cls, analysis: MealAnalysis) -> NutritionalAnalysisResponse:
        """Project an application :class:`MealAnalysis` onto the wire shape (AIA-301, AIA-302).

        ``nutritionalInfo`` and ``alignment`` are ``None`` when the model could not estimate the
        meal (and so there was nothing to score); ``alignment`` exposes its score as a 0-100
        percentage; ``disclaimer`` carries the AIA-505 medical disclaimer.
        """
        nutrition = analysis.nutrition
        alignment = analysis.alignment
        return cls(
            nutritional_info=(
                NutritionalInfoSchema(
                    calories=nutrition.calories,
                    protein=nutrition.protein,
                    carbs=nutrition.carbs,
                    fat=nutrition.fat,
                    sugar=nutrition.sugar,
                )
                if nutrition is not None
                else None
            ),
            alignment=(
                NutritionalAlignmentResponse(
                    score=alignment.percentage,
                    details=alignment.details,
                )
                if alignment is not None
                else None
            ),
            warnings=list(analysis.warnings),
            disclaimer=analysis.disclaimer,
        )


class MealPlanStatus(StrEnum):
    """Lifecycle status of a meal plan (contract ``MealPlanResponse.status``)."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    SAVED = "saved"


class OptimizationGoal(StrEnum):
    """What ``POST /ai/optimize-plan`` should prioritize (contract ``OptimizePlanRequest.goal``)."""

    BALANCE_MACROS = "balance_macros"
    INCREASE_PROTEIN = "increase_protein"
    REDUCE_CALORIES = "reduce_calories"
    INCREASE_SATISFACTION = "increase_satisfaction"


class OptimizePlanRequest(_Camel):
    """The validated request envelope for ``POST /ai/optimize-plan`` (AIA-401).

    ``planId`` is a required UUID (a malformed id is rejected with ``422`` before any work is done).
    ``goal`` is optional — the contract only requires ``planId`` — and steers optimization in
    AIA-403+.
    """

    plan_id: UUID
    goal: OptimizationGoal | None = None


class NutritionalTargetsSchema(_Camel):
    """A plan's nutrition goals (``NutritionalTargets``): daily calories + optional macro grams."""

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


class NutritionalSummarySchema(_Camel):
    """``NutritionalSummary`` — the plan's total + daily-average nutrition versus its targets."""

    total: NutritionalInfoSchema
    daily_average: NutritionalInfoSchema
    targets: NutritionalTargetsSchema

    @classmethod
    def from_summary(cls, summary: PlanNutritionSummary) -> NutritionalSummarySchema:
        return cls(
            total=_nutrition_schema(summary.total),
            daily_average=_nutrition_schema(summary.daily_average),
            targets=NutritionalTargetsSchema(
                calories=summary.targets.calories,
                protein=summary.targets.protein,
                carbs=summary.targets.carbs,
                fat=summary.targets.fat,
                sugar=summary.targets.sugar,
            ),
        )


class MealResponse(_Camel):
    """``MealResponse`` — one planned meal. The recipe stays ``null`` on plan reads."""

    id: str
    meal_type: MealType
    servings: float
    recipe: RecipeResponse | None = None
    nutritional_info: NutritionalInfoSchema | None = None

    @classmethod
    def from_meal(cls, meal: OptimizationMeal) -> MealResponse:
        return cls(
            id=meal.id,
            meal_type=MealType(meal.meal_type),
            servings=meal.servings,
            nutritional_info=(
                _nutrition_schema(meal.nutrition) if meal.nutrition is not None else None
            ),
        )


class MealPlanResponse(_Camel):
    """``MealPlanResponse`` — the caller-facing projection of a meal plan (AIA-401).

    Returned by ``POST /ai/optimize-plan``; the same wire shape the dietary service serves, so the
    optimized plan reads identically to a plan fetched directly.
    """

    id: str
    name: str
    start_date: date
    end_date: date
    daily_calorie_target: int
    status: MealPlanStatus
    meals: list[MealResponse] = Field(default_factory=list)
    nutritional_summary: NutritionalSummarySchema | None = None

    @classmethod
    def from_plan(cls, plan: OptimizationPlan) -> MealPlanResponse:
        return cls(
            id=plan.id,
            name=plan.name,
            start_date=plan.start_date,
            end_date=plan.end_date,
            daily_calorie_target=plan.daily_calorie_target,
            status=MealPlanStatus(plan.status),
            meals=[MealResponse.from_meal(meal) for meal in plan.meals],
            nutritional_summary=(
                NutritionalSummarySchema.from_summary(plan.nutritional_summary)
                if plan.nutritional_summary is not None
                else None
            ),
        )


def _nutrition_schema(nutrition: PlanNutrition) -> NutritionalInfoSchema:
    """Project a plan-nutrition value object onto the wire shape."""
    return NutritionalInfoSchema(
        calories=nutrition.calories,
        protein=nutrition.protein,
        carbs=nutrition.carbs,
        fat=nutrition.fat,
        sugar=nutrition.sugar,
    )
