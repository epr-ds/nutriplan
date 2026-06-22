"""DPL-201: MongoRecipeRepository round-trips recipes (ingredients + per-serving nutrition)."""

from app.db.mongo import recipes
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from app.repositories.mongo_recipe_repository import MongoRecipeRepository


def _recipe(**overrides) -> Recipe:
    data = dict(
        name="Oatmeal",
        servings=2,
        ingredients=[
            Ingredient(name="Rolled oats", quantity=80.0, unit="g", calories=300, protein=10.5)
        ],
        instructions=["Boil water", "Stir in oats"],
        prep_time=5,
        cook_time=10,
        nutritional_info=NutritionalInfo(
            calories=320, protein=12.0, carbs=55.0, fat=6.0, sugar=2.0
        ),
    )
    data.update(overrides)
    return Recipe.create(**data)


def test_add_then_get_round_trips(mongo_db):
    repo = MongoRecipeRepository(recipes(mongo_db))
    recipe = _recipe()
    repo.add(recipe)

    fetched = repo.get(recipe.id)

    assert fetched is not None
    assert fetched.id == recipe.id
    assert fetched.name == "Oatmeal"
    assert fetched.servings == 2
    assert fetched.ingredients[0].name == "Rolled oats"
    assert fetched.ingredients[0].unit == "g"
    # Per-serving nutrition persisted (DPL-201 AC).
    assert fetched.nutritional_info.calories == 320


def test_get_unknown_returns_none(mongo_db):
    repo = MongoRecipeRepository(recipes(mongo_db))
    assert repo.get("does-not-exist") is None
