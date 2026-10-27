"""DPL-205: recipe data validation, unit normalization and nutrition bounds.

Covers the acceptance criteria of `DPL-205` (GitHub issue #98): the curated recipe catalog must
carry normalized units, nutrition values that honour bounds, and a validation report over the
dataset — so that bad rows are rejected instead of silently trusted.
"""

from __future__ import annotations

import pytest

from app.db.seed import SEED_RECIPES
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from app.domain.recipe_validation import (
    RecipeValidationReport,
    validate_recipes,
)


def _recipe(**overrides) -> Recipe:
    kwargs: dict = {"name": "Test Recipe", "servings": 2}
    kwargs.update(overrides)
    return Recipe.create(**kwargs)


def test_create_normalizes_ingredient_units_to_canonical_form():
    recipe = _recipe(ingredients=[Ingredient(name="Rolled oats", quantity=80.0, unit="Grams")])

    assert recipe.ingredients[0].unit == "g"


def test_create_rejects_negative_nutritional_info():
    with pytest.raises(ValueError):
        Recipe.create(
            name="Bad Recipe",
            servings=2,
            nutritional_info=NutritionalInfo(
                calories=-5, protein=-1.0, carbs=-2.0, fat=-3.0, sugar=-4.0
            ),
        )


def test_create_rejects_negative_ingredient_quantity():
    with pytest.raises(ValueError):
        Recipe.create(
            name="Bad Recipe", servings=2, ingredients=[Ingredient(name="Oats", quantity=-1.0)]
        )


def test_validation_report_over_seed_catalog_is_clean():
    report = validate_recipes(SEED_RECIPES)

    assert isinstance(report, RecipeValidationReport)
    assert report.total == len(SEED_RECIPES)
    assert report.invalid == 0
    assert report.ok
