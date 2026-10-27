"""DPL-706 — Recipe data quality tests (schema, bounds, es/en).

The curated recipe catalog (``app.db.seed``, DPL-201/DPL-204) must stay data-quality clean:
stable unique ids, in-bounds nutrition, and bilingual (es/en) content for the locales the app
serves. These tests pin the invariants on the shipped catalog.
"""

from __future__ import annotations

from app.db.seed import SEED_RECIPES


def test_seed_catalog_recipes_are_unique() -> None:
    """Every curated recipe must carry a stable, unique id (no duplicate catalog rows)."""
    ids = [recipe.id for recipe in SEED_RECIPES]
    assert len(ids) == len(set(ids)), "duplicate recipe ids in the curated catalog"


def test_seed_catalog_recipes_meet_nutrition_bounds() -> None:
    """Every curated recipe must have positive servings and positive per-serving nutrition."""
    for recipe in SEED_RECIPES:
        assert recipe.servings > 0, recipe.id
        assert recipe.nutritional_info is not None, recipe.id
        assert recipe.nutritional_info.calories is not None and recipe.nutritional_info.calories > 0, (
            recipe.id
        )


def test_seed_catalog_recipes_provide_bilingual_content() -> None:
    """DPL-706: every curated recipe must provide es and en names + descriptions."""
    for recipe in SEED_RECIPES:
        assert recipe.name.strip(), recipe.id
        assert recipe.description, recipe.id
        # Bilingual coverage: the es (Spanish) name + description must exist per locale.
        assert getattr(recipe, "name_es", None), f"missing Spanish name for {recipe.id}"
        assert getattr(recipe, "description_es", None), f"missing Spanish description for {recipe.id}"