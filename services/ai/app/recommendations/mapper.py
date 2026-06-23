"""Map a validated model draft onto recommended recipes (AIA-203).

For each recipe the model proposed, the mapper prefers a **real** catalogue recipe with the same
name (AC1); when there is no match it **synthesizes** a complete recipe from the model's own output
(AC2). The synthesized recipe keeps the proposed ingredients, steps, and nutrition and is given a
deterministic slug id, so every result -- linked or synthesized -- is a full, usable recipe.
"""

from __future__ import annotations

import re

from app.recommendations.catalogue import RecipeCatalogue
from app.recommendations.draft import RecipeDraft, RecommendationDraft
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    """Turn a recipe name into a stable, url-friendly id for a synthesized recipe."""
    slug = _NON_SLUG.sub("-", name.strip().casefold()).strip("-")
    return slug or "recipe"


class RecipeMapper:
    """Turn a :class:`RecommendationDraft` into linked-or-synthesized recipes."""

    def __init__(self, catalogue: RecipeCatalogue) -> None:
        self._catalogue = catalogue

    def map(self, draft: RecommendationDraft) -> list[RecommendedRecipe]:
        """Resolve every drafted recipe to a catalogue match or a synthesized recipe."""
        return [self._resolve(recipe) for recipe in draft.recipes]

    def _resolve(self, recipe: RecipeDraft) -> RecommendedRecipe:
        match = self._catalogue.find(recipe.name)
        return match if match is not None else _synthesize(recipe)


def _synthesize(recipe: RecipeDraft) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=_slug(recipe.name),
        name=recipe.name,
        servings=recipe.servings,
        ingredients=tuple(
            RecommendedIngredient(name=item.name, quantity=item.quantity, unit=item.unit)
            for item in recipe.ingredients
        ),
        instructions=tuple(recipe.instructions),
        nutrition=RecommendedNutrition(
            calories=recipe.nutrition.calories,
            protein=recipe.nutrition.protein,
            carbs=recipe.nutrition.carbs,
            fat=recipe.nutrition.fat,
            sugar=recipe.nutrition.sugar,
        ),
        source=RecipeSource.SYNTHESIZED,
        description=recipe.description,
        prep_time_minutes=recipe.prep_time_minutes,
        cook_time_minutes=recipe.cook_time_minutes,
        dietary_types=tuple(recipe.dietary_types),
    )
