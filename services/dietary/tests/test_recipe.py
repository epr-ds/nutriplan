"""DPL-201: Recipe aggregate — factory invariants, value objects, document round-trip."""

import pytest

from app.domain.recipe import Ingredient, NutritionalInfo, Recipe


def _ingredient(**overrides) -> Ingredient:
    data = dict(
        name="Rolled oats",
        quantity=80.0,
        unit="g",
        calories=300,
        protein=10.5,
        carbs=54.0,
        fat=5.0,
        sugar=1.2,
    )
    data.update(overrides)
    return Ingredient(**data)


def test_create_assigns_id_and_defaults():
    recipe = Recipe.create(name="Oatmeal", servings=2)

    assert recipe.id
    assert recipe.servings == 2
    assert recipe.ingredients == []
    assert recipe.instructions == []
    assert recipe.created_at is not None
    assert recipe.updated_at is not None


def test_create_requires_positive_servings():
    with pytest.raises(ValueError):
        Recipe.create(name="Oatmeal", servings=0)


def test_create_rejects_blank_name():
    with pytest.raises(ValueError):
        Recipe.create(name="", servings=1)


def test_create_holds_ingredients_and_per_serving_nutrition():
    nutrition = NutritionalInfo(calories=320, protein=12.0, carbs=55.0, fat=6.0, sugar=2.0)

    recipe = Recipe.create(
        name="Oatmeal",
        servings=2,
        description="Warm oats",
        ingredients=[_ingredient()],
        instructions=["Boil water", "Stir in oats"],
        prep_time=5,
        cook_time=10,
        image_url="https://img.example/oatmeal.png",
        nutritional_info=nutrition,
    )

    assert len(recipe.ingredients) == 1
    assert recipe.ingredients[0].name == "Rolled oats"
    assert recipe.instructions == ["Boil water", "Stir in oats"]
    # Per-serving nutrition is stored on the recipe (DPL-201 AC).
    assert recipe.nutritional_info.calories == 320


def test_to_document_uses_id_as_underscore_id_with_camelcase_keys():
    recipe = Recipe.create(
        name="Oatmeal",
        servings=2,
        prep_time=5,
        ingredients=[_ingredient()],
        nutritional_info=NutritionalInfo(calories=320, protein=12.0),
    )

    doc = recipe.to_document()

    assert doc["_id"] == recipe.id
    assert "id" not in doc
    assert doc["prepTime"] == 5
    assert doc["ingredients"][0]["name"] == "Rolled oats"
    assert doc["nutritionalInfo"]["calories"] == 320
    assert isinstance(doc["createdAt"], str)


def test_from_document_round_trips():
    recipe = Recipe.create(
        name="Oatmeal",
        servings=2,
        ingredients=[_ingredient()],
        nutritional_info=NutritionalInfo(calories=320),
    )

    rehydrated = Recipe.from_document(recipe.to_document())

    assert rehydrated.id == recipe.id
    assert rehydrated.name == "Oatmeal"
    assert rehydrated.servings == 2
    assert rehydrated.ingredients[0].unit == "g"
    assert rehydrated.nutritional_info.calories == 320
