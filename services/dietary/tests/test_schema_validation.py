"""DPL-101: the meal_plans collection enforces schema validation on write."""

import pytest
from pymongo.errors import WriteError

from app.db.mongo import MEAL_PLANS


def _valid_doc(**overrides) -> dict:
    doc = {
        "_id": "plan-ok",
        "userId": "u",
        "name": "Valid",
        "startDate": "2026-01-01",
        "endDate": "2026-01-07",
        "dailyCalorieTarget": 2000,
        "status": "draft",
        "meals": [],
        "createdAt": "2026-01-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def test_valid_document_accepted(mongo_db):
    res = mongo_db[MEAL_PLANS].insert_one(_valid_doc())
    assert res.inserted_id == "plan-ok"


def test_missing_required_field_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[MEAL_PLANS].insert_one({"_id": "x", "userId": "u"})


def test_invalid_status_enum_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[MEAL_PLANS].insert_one(_valid_doc(_id="bad-status", status="bogus"))


def test_invalid_meal_type_enum_rejected(mongo_db):
    bad_meal = [{"id": "m1", "mealType": "brunch", "recipeId": "r1", "servings": 1.0}]
    with pytest.raises(WriteError):
        mongo_db[MEAL_PLANS].insert_one(_valid_doc(_id="bad-meal", meals=bad_meal))


def test_wrong_type_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[MEAL_PLANS].insert_one(_valid_doc(_id="bad-type", dailyCalorieTarget="lots"))
