"""Recommendation use case: request -> preference-aware prompt -> real recipes + alignment.

This is the application layer for ``POST /ai/recommendations``. AIA-202 ships the prompt half: a
:class:`RecommendationCommand` plus a :class:`RecommendationPromptAssembler` that renders a
distinct, localized template per context, with the caller's dietary profile injected. AIA-203 adds
the LLM call and recipe mapping: a :class:`RecommendationService` asks the model for a
schema-constrained :class:`RecommendationDraft`, and a :class:`RecipeMapper` turns it into
``RecommendedRecipe`` results -- linking real catalogue recipes where possible and synthesizing the
rest. AIA-204 completes the result: the service surfaces the model's ``reasoning`` and a
:class:`RecommendationAligner` scores the recipes against the caller's targets/preferences (AIA-106)
into a :class:`RecommendationAlignment`. AIA-205 keeps results fresh: a
:class:`RecommendationDiversifier` (configurable :class:`VarietyStrength`) drops recipes repeating
the user's ``previousMeals`` and de-duplicates look-alikes before they are scored. AIA-501 adds the
safety net: an :class:`AllergenFilter` removes any recipe that violates the caller's allergies or
excluded ingredients and records the removal through a :class:`GuardrailTelemetry` port. AIA-502
adds the nutritional-bounds net: a :class:`NutritionBoundsGuard` clamps the request's calorie
targets into sane bounds and rejects any recommended recipe whose nutrition is physically
impossible, recording both through a :class:`BoundsTelemetry` port.
"""

from app.recommendations.alignment import (
    RecipeAlignment,
    RecommendationAligner,
    RecommendationAlignment,
)
from app.recommendations.assembler import (
    RecommendationPromptAssembler,
    build_recommendation_prompt_assembler,
)
from app.recommendations.bounds import (
    MAX_DAILY_CALORIES,
    MIN_DAILY_CALORIES,
    BoundsReason,
    BoundsTelemetry,
    BoundsViolation,
    CalorieClamp,
    InMemoryBoundsTelemetry,
    LoggingBoundsTelemetry,
    NutritionBoundsGuard,
)
from app.recommendations.catalogue import (
    InMemoryRecipeCatalogue,
    RecipeCatalogue,
    normalize_name,
)
from app.recommendations.commands import (
    MacroTargets,
    MealType,
    RecommendationCommand,
    RecommendationContext,
)
from app.recommendations.draft import (
    IngredientDraft,
    NutritionDraft,
    RecipeDraft,
    RecommendationDraft,
)
from app.recommendations.mapper import RecipeMapper
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.safety import (
    AllergenFilter,
    GuardrailTelemetry,
    GuardrailViolation,
    InMemoryGuardrailTelemetry,
    LoggingGuardrailTelemetry,
    ViolationKind,
)
from app.recommendations.service import (
    RecommendationResult,
    RecommendationService,
    build_recommendation_service,
)
from app.recommendations.variety import (
    RecommendationDiversifier,
    VarietyPolicy,
    VarietyStrength,
    build_diversifier,
)

__all__ = [
    "MAX_DAILY_CALORIES",
    "MIN_DAILY_CALORIES",
    "AllergenFilter",
    "BoundsReason",
    "BoundsTelemetry",
    "BoundsViolation",
    "CalorieClamp",
    "GuardrailTelemetry",
    "GuardrailViolation",
    "InMemoryBoundsTelemetry",
    "InMemoryGuardrailTelemetry",
    "InMemoryRecipeCatalogue",
    "IngredientDraft",
    "LoggingBoundsTelemetry",
    "LoggingGuardrailTelemetry",
    "MacroTargets",
    "MealType",
    "NutritionBoundsGuard",
    "NutritionDraft",
    "RecipeAlignment",
    "RecipeCatalogue",
    "RecipeDraft",
    "RecipeMapper",
    "RecipeSource",
    "RecommendationAligner",
    "RecommendationAlignment",
    "RecommendationCommand",
    "RecommendationContext",
    "RecommendationDiversifier",
    "RecommendationDraft",
    "RecommendationPromptAssembler",
    "RecommendationResult",
    "RecommendationService",
    "RecommendedIngredient",
    "RecommendedNutrition",
    "RecommendedRecipe",
    "ViolationKind",
    "VarietyPolicy",
    "VarietyStrength",
    "build_diversifier",
    "build_recommendation_prompt_assembler",
    "build_recommendation_service",
    "normalize_name",
]
