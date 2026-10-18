"""DPL-202/206: recipe search against MongoDB (filters, ingredient OR-match + ranking)."""

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


def test_ingredients_match_any_case_insensitive(repo):
    assert _names(repo.search(ingredients=["broccoli"])) == ["Tofu Stir-Fry"]
    assert _names(repo.search(ingredients=["FIRM TOFU", "broccoli"])) == ["Tofu Stir-Fry"]
    # OR semantics (DPL-206): names spread across recipes match each recipe containing any of them.
    assert _names(repo.search(ingredients=["firm tofu", "rolled oats"])) == [
        "Oats",
        "Tofu Stir-Fry",
    ]


def test_ingredients_ranked_by_overlap(repo):
    # Tofu matches two requested names, Chicken only one: overlap outranks alphabetical order.
    results = repo.search(ingredients=["firm tofu", "broccoli", "chicken breast"])
    assert _names(results) == ["Tofu Stir-Fry", "Chicken Bowl"]


def test_ingredient_overlap_tie_broken_by_name(repo):
    # Both match exactly one requested ingredient -> alphabetical (name, id) tie-break.
    assert _names(repo.search(ingredients=["milk", "salmon fillet"])) == ["Oats", "Salmon"]


def test_pagination_respects_relevance_order(repo):
    query = {"ingredients": ["firm tofu", "broccoli", "chicken breast"]}
    assert _names(repo.search(**query, limit=1)) == ["Tofu Stir-Fry"]
    assert _names(repo.search(**query, skip=1, limit=1)) == ["Chicken Bowl"]


def test_macro_filters_combine_with_ingredient_match(repo):
    # Both match an ingredient; only Tofu also clears the protein floor.
    results = repo.search(ingredients=["firm tofu", "rolled oats"], min_protein=20)
    assert _names(results) == ["Tofu Stir-Fry"]
    # Both match and are under the calorie cap -> both, overlap tie -> name order.
    results = repo.search(ingredients=["firm tofu", "rolled oats"], max_calories=250)
    assert _names(results) == ["Oats", "Tofu Stir-Fry"]


def test_combined_filters(repo):
    results = repo.search(diet_type=DietaryType.VEGETARIAN, max_calories=250, min_protein=20)
    assert _names(results) == ["Tofu Stir-Fry"]


def test_pagination_is_stable(repo):
    assert _names(repo.search(skip=0, limit=2)) == ["Chicken Bowl", "Oats"]
    assert _names(repo.search(skip=2, limit=2)) == ["Salmon", "Tofu Stir-Fry"]
