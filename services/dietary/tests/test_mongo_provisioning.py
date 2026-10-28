"""DPL-803: the per-boot provisioning entry point installs the indexes and seeds the catalog."""

from __future__ import annotations

from app.db.mongo import FAVORITES, MEAL_PLANS, RECIPES
from app.db.provisioning import provision_dietary


def _index_keys(db, collection) -> set[tuple]:
    return {tuple(index["key"].keys()) for index in db[collection].list_indexes()}


def test_provisioning_installs_the_catalog_indexes_and_seeds_the_catalog(mongo_db) -> None:
    """DPL-803: provisioning installs the DPL-101/DPL-202 indexes and the seeded catalog."""
    provision_dietary(mongo_db)

    meal_plan_indexes = _index_keys(mongo_db, MEAL_PLANS)
    assert ("userId",) in meal_plan_indexes
    assert ("userId", "status") in meal_plan_indexes
    assert ("userId", "startDate", "endDate") in meal_plan_indexes

    recipe_indexes = {tuple(index["key"].keys()) for index in mongo_db[RECIPES].list_indexes()}
    assert ("ingredients.name",) in recipe_indexes
    assert ("nutritionalInfo.calories",) in recipe_indexes
    assert ("dietaryTypes",) in recipe_indexes

    assert len(list(mongo_db[RECIPES].find({}, {"_id": 1}))) > 0


def test_provisioning_is_idempotent(mongo_db) -> None:
    """DPL-803: provisioning is safe to run on every boot (idempotent upserts)."""
    provision_dietary(mongo_db)
    provision_dietary(mongo_db)

    assert len(list(mongo_db[RECIPES].find({}, {"_id": 1}))) > 0
    assert len(list(mongo_db[FAVORITES].list_indexes())) > 0
