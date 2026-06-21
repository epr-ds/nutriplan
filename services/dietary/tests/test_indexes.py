"""DPL-101: required indexes exist on meal_plans (userId, status, date range)."""

from app.db.mongo import MEAL_PLANS


def _index_key_sets(mongo_db) -> list[list[str]]:
    return [list(ix["key"].keys()) for ix in mongo_db[MEAL_PLANS].list_indexes()]


def test_userid_index_present(mongo_db):
    assert ["userId"] in _index_key_sets(mongo_db)


def test_status_index_present(mongo_db):
    assert ["userId", "status"] in _index_key_sets(mongo_db)


def test_date_range_index_present(mongo_db):
    assert ["userId", "startDate", "endDate"] in _index_key_sets(mongo_db)
