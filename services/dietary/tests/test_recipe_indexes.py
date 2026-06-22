"""DPL-201: required indexes exist on recipes (ingredient name + per-serving macros)."""

from app.db.mongo import RECIPES


def _index_key_sets(mongo_db) -> list[list[str]]:
    return [list(ix["key"].keys()) for ix in mongo_db[RECIPES].list_indexes()]


def test_ingredient_name_index_present(mongo_db):
    assert ["ingredients.name"] in _index_key_sets(mongo_db)


def test_calorie_index_present(mongo_db):
    assert ["nutritionalInfo.calories"] in _index_key_sets(mongo_db)


def test_protein_index_present(mongo_db):
    assert ["nutritionalInfo.protein"] in _index_key_sets(mongo_db)


def test_carbs_index_present(mongo_db):
    assert ["nutritionalInfo.carbs"] in _index_key_sets(mongo_db)


def test_fat_index_present(mongo_db):
    assert ["nutritionalInfo.fat"] in _index_key_sets(mongo_db)
