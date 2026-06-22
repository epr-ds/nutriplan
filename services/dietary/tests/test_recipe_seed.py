"""DPL-201: the reference recipe catalog seeds idempotently and is retrievable."""

from app.db.mongo import RECIPES, recipes
from app.db.seed import SEED_RECIPES, seed_recipes
from app.repositories.mongo_recipe_repository import MongoRecipeRepository


def test_seed_inserts_catalog(mongo_db):
    count = seed_recipes(recipes(mongo_db))

    assert count == len(SEED_RECIPES)
    assert mongo_db[RECIPES].count_documents({}) == len(SEED_RECIPES)


def test_seed_is_idempotent(mongo_db):
    seed_recipes(recipes(mongo_db))
    seed_recipes(recipes(mongo_db))  # a second run must not duplicate

    assert mongo_db[RECIPES].count_documents({}) == len(SEED_RECIPES)


def test_seeded_recipes_are_retrievable_with_nutrition(mongo_db):
    seed_recipes(recipes(mongo_db))
    repo = MongoRecipeRepository(recipes(mongo_db))

    for seed in SEED_RECIPES:
        fetched = repo.get(seed.id)
        assert fetched is not None
        assert fetched.name == seed.name
        assert fetched.servings >= 1
        # Each catalog recipe stores its per-serving nutrition (DPL-201 AC).
        assert fetched.nutritional_info is not None
