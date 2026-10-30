"""DPL-204 — curated recipe dataset coverage (seed catalog).

The curated baseline catalog (``app.db.seed``) is the fallback the app ships with until
authoring UI exists; DPL-204 requires it to cover >=150 curated recipes with verified
per-serving nutrition (epic E2, sprint 8).
"""

from __future__ import annotations

from app.db.seed import SEED_RECIPES


def test_seed_catalog_covers_150_curated_recipes() -> None:
    """The curated baseline catalog must ship at least 150 recipes (DPL-204 AC1)."""
    assert len(SEED_RECIPES) >= 150


def test_seed_catalog_recipes_carry_verified_per_serving_nutrition() -> None:
    """Every curated recipe must carry verified per-serving nutrition (DPL-204 AC3)."""
    for recipe in SEED_RECIPES:
        assert recipe.nutritional_info is not None, recipe.id
        assert recipe.nutritional_info.calories > 0, recipe.id
