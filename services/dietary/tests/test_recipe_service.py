"""DPL-202 application-layer tests: recipe search use case (Mongo-free)."""

import pytest

from app.application.commands import SearchRecipesQuery
from app.application.recipe_service import RecipeService
from app.domain.dietary_types import DietaryType
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from tests.fakes import InMemoryRecipeRepository


def _recipe(name, *, ingredients=(), calories=None, protein=None, diets=()):
    return Recipe.create(
        name=name,
        servings=2,
        ingredients=[Ingredient(name=i) for i in ingredients],
        nutritional_info=NutritionalInfo(calories=calories, protein=protein),
        dietary_types=list(diets),
    )


@pytest.fixture
def service() -> RecipeService:
    repo = InMemoryRecipeRepository()
    repo.add(
        _recipe(
            "Oats",
            ingredients=["Rolled oats", "Milk"],
            calories=243,
            protein=9.9,
            diets=[DietaryType.VEGETARIAN],
        )
    )
    repo.add(
        _recipe(
            "Tofu Stir-Fry",
            ingredients=["Firm tofu", "Broccoli"],
            calories=228,
            protein=23.5,
            diets=[DietaryType.VEGAN, DietaryType.VEGETARIAN],
        )
    )
    repo.add(
        _recipe(
            "Chicken Bowl",
            ingredients=["Chicken breast", "Quinoa"],
            calories=550,
            protein=55.0,
            diets=[DietaryType.OMNIVORE],
        )
    )
    repo.add(
        _recipe(
            "Salmon",
            ingredients=["Salmon fillet", "Zucchini"],
            calories=473,
            protein=32.3,
            diets=[DietaryType.PALEO],
        )
    )
    return RecipeService(repo)


def _names(recipes) -> list[str]:
    return [r.name for r in recipes]


def test_empty_query_returns_all_sorted_by_name(service):
    results = service.search_recipes(SearchRecipesQuery())
    assert _names(results) == ["Chicken Bowl", "Oats", "Salmon", "Tofu Stir-Fry"]


def test_filter_by_diet_type_vegan(service):
    results = service.search_recipes(SearchRecipesQuery(diet_type=DietaryType.VEGAN))
    assert _names(results) == ["Tofu Stir-Fry"]


def test_filter_by_diet_type_vegetarian_matches_multiple(service):
    results = service.search_recipes(SearchRecipesQuery(diet_type=DietaryType.VEGETARIAN))
    assert _names(results) == ["Oats", "Tofu Stir-Fry"]


def test_filter_by_max_calories(service):
    results = service.search_recipes(SearchRecipesQuery(max_calories=250))
    assert _names(results) == ["Oats", "Tofu Stir-Fry"]


def test_filter_by_min_protein(service):
    results = service.search_recipes(SearchRecipesQuery(min_protein=30))
    assert _names(results) == ["Chicken Bowl", "Salmon"]


def test_ingredients_are_case_insensitive_and_require_all(service):
    one = service.search_recipes(SearchRecipesQuery(ingredients=("broccoli",)))
    assert _names(one) == ["Tofu Stir-Fry"]

    both = service.search_recipes(SearchRecipesQuery(ingredients=("FIRM TOFU", "broccoli")))
    assert _names(both) == ["Tofu Stir-Fry"]

    # Requiring all: ingredients spread across different recipes match nothing.
    assert (
        service.search_recipes(SearchRecipesQuery(ingredients=("firm tofu", "rolled oats"))) == []
    )


def test_filters_combine_with_and(service):
    query = SearchRecipesQuery(diet_type=DietaryType.VEGETARIAN, max_calories=250, min_protein=20)
    assert _names(service.search_recipes(query)) == ["Tofu Stir-Fry"]


def test_pagination_is_stable_and_non_overlapping(service):
    page1 = service.search_recipes(SearchRecipesQuery(page=1, limit=2))
    page2 = service.search_recipes(SearchRecipesQuery(page=2, limit=2))

    assert _names(page1) == ["Chicken Bowl", "Oats"]
    assert _names(page2) == ["Salmon", "Tofu Stir-Fry"]
    assert set(_names(page1)).isdisjoint(_names(page2))


def test_over_broad_query_bounded_by_limit(service):
    results = service.search_recipes(SearchRecipesQuery(limit=3))
    assert len(results) == 3
