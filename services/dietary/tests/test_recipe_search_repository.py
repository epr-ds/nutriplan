"""DPL-202: recipe search against MongoDB (filters, AND ingredients, sort, pagination)."""

import pytest

from app.db.mongo import recipes
from app.domain.dietary_types import DietaryType
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from app.repositories.mongo_recipe_repository import MongoRecipeRepository


def _recipe(name, *, ingredients=(), calories=None, protein=None, diets=()):
    return Recipe.create(
        name=name,
        servings=2,
        ingredients=[Ingredient(name=i) for i in ingredients],
        nutritional_info=NutritionalInfo(calories=calories, protein=protein),
        dietary_types=list(diets),
    )


@pytest.fixture
def repo(mongo_db) -> MongoRecipeRepository:
    r = MongoRecipeRepository(recipes(mongo_db))
    r.add(
        _recipe(
            "Oats",
            ingredients=["Rolled oats", "Milk"],
            calories=243,
            protein=9.9,
            diets=[DietaryType.VEGETARIAN],
        )
    )
    r.add(
        _recipe(
            "Tofu Stir-Fry",
            ingredients=["Firm tofu", "Broccoli"],
            calories=228,
            protein=23.5,
            diets=[DietaryType.VEGAN, DietaryType.VEGETARIAN],
        )
    )
    r.add(
        _recipe(
            "Chicken Bowl",
            ingredients=["Chicken breast", "Quinoa"],
            calories=550,
            protein=55.0,
            diets=[DietaryType.OMNIVORE],
        )
    )
    r.add(
        _recipe(
            "Salmon",
            ingredients=["Salmon fillet", "Zucchini"],
            calories=473,
            protein=32.3,
            diets=[DietaryType.PALEO],
        )
    )
    return r


def _names(rs) -> list[str]:
    return [r.name for r in rs]


def test_no_filters_returns_all_name_sorted(repo):
    assert _names(repo.search()) == ["Chicken Bowl", "Oats", "Salmon", "Tofu Stir-Fry"]


def test_diet_type_filter(repo):
    assert _names(repo.search(diet_type=DietaryType.VEGETARIAN)) == ["Oats", "Tofu Stir-Fry"]
    assert _names(repo.search(diet_type=DietaryType.VEGAN)) == ["Tofu Stir-Fry"]


def test_max_calories_filter(repo):
    assert _names(repo.search(max_calories=250)) == ["Oats", "Tofu Stir-Fry"]


def test_min_protein_filter(repo):
    assert _names(repo.search(min_protein=30)) == ["Chicken Bowl", "Salmon"]


def test_ingredients_require_all_case_insensitive(repo):
    assert _names(repo.search(ingredients=["broccoli"])) == ["Tofu Stir-Fry"]
    assert _names(repo.search(ingredients=["FIRM TOFU", "broccoli"])) == ["Tofu Stir-Fry"]
    # Ingredients spread across different recipes match nothing (AND semantics).
    assert repo.search(ingredients=["firm tofu", "rolled oats"]) == []


def test_combined_filters(repo):
    results = repo.search(diet_type=DietaryType.VEGETARIAN, max_calories=250, min_protein=20)
    assert _names(results) == ["Tofu Stir-Fry"]


def test_pagination_is_stable(repo):
    assert _names(repo.search(skip=0, limit=2)) == ["Chicken Bowl", "Oats"]
    assert _names(repo.search(skip=2, limit=2)) == ["Salmon", "Tofu Stir-Fry"]
