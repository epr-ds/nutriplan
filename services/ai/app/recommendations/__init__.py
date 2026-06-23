"""Recommendation use case: request -> preference-aware prompt -> real recipes (AIA-202, AIA-203).

This is the application layer for ``POST /ai/recommendations``. AIA-202 ships the prompt half: a
:class:`RecommendationCommand` plus a :class:`RecommendationPromptAssembler` that renders a
distinct, localized template per context, with the caller's dietary profile injected. AIA-203 adds
the LLM call and recipe mapping: a :class:`RecommendationService` asks the model for a
schema-constrained :class:`RecommendationDraft`, and a :class:`RecipeMapper` turns it into
``RecommendedRecipe`` results -- linking real catalogue recipes where possible and synthesizing the
rest. Nutritional alignment and reasoning (AIA-204) layer on top later.
"""

from app.recommendations.assembler import (
    RecommendationPromptAssembler,
    build_recommendation_prompt_assembler,
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
from app.recommendations.service import (
    RecommendationService,
    build_recommendation_service,
)

__all__ = [
    "InMemoryRecipeCatalogue",
    "IngredientDraft",
    "MacroTargets",
    "MealType",
    "NutritionDraft",
    "RecipeCatalogue",
    "RecipeDraft",
    "RecipeMapper",
    "RecipeSource",
    "RecommendationCommand",
    "RecommendationContext",
    "RecommendationDraft",
    "RecommendationPromptAssembler",
    "RecommendationService",
    "RecommendedIngredient",
    "RecommendedNutrition",
    "RecommendedRecipe",
    "build_recommendation_prompt_assembler",
    "build_recommendation_service",
    "normalize_name",
]
