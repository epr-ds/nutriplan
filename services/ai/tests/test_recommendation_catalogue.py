"""Tests for the in-memory recipe catalogue adapter (AIA-203, AC1).

The catalogue is the port the mapper consults to link a recommendation to a *real*
recipe. The in-memory adapter matches by a normalized name so trivial differences in
casing or surrounding whitespace still resolve to the same catalogue entry.
"""

from __future__ import annotations

from app.recommendations.catalogue import InMemoryRecipeCatalogue
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


def _catalogue_recipe(name: str, *, recipe_id: str = "recipe-1") -> RecommendedRecipe:
    return RecommendedRecipe(
        id=recipe_id,
        name=name,
        servings=2,
        ingredients=(RecommendedIngredient(name="oats", quantity=80, unit="g"),),
        instructions=("Cook the oats.",),
        nutrition=RecommendedNutrition(calories=350, protein=12, carbs=60, fat=7),
        source=RecipeSource.CATALOGUE,
    )


def test_find_returns_the_matching_recipe() -> None:
    recipe = _catalogue_recipe("Oatmeal Bowl", recipe_id="recipe-oatmeal")
    catalogue = InMemoryRecipeCatalogue([recipe])

    assert catalogue.find("Oatmeal Bowl") is recipe


def test_find_normalizes_case_and_whitespace() -> None:
    recipe = _catalogue_recipe("Oatmeal Bowl")
    catalogue = InMemoryRecipeCatalogue([recipe])

    assert catalogue.find("  oatmeal   bowl ") is recipe


def test_find_returns_none_on_miss() -> None:
    catalogue = InMemoryRecipeCatalogue([_catalogue_recipe("Oatmeal Bowl")])

    assert catalogue.find("Grilled Salmon") is None


def test_empty_catalogue_finds_nothing() -> None:
    assert InMemoryRecipeCatalogue().find("anything") is None
