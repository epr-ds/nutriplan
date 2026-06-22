"""DPL-201: the recipes collection enforces schema validation on write."""

import pytest
from pymongo.errors import WriteError

from app.db.mongo import RECIPES


def _valid_doc(**overrides) -> dict:
    doc = {
        "_id": "recipe-ok",
        "name": "Valid",
        "servings": 2,
        "ingredients": [{"name": "Oats", "quantity": 80.0, "calories": 300}],
        "createdAt": "2024-01-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def test_valid_document_accepted(mongo_db):
    res = mongo_db[RECIPES].insert_one(_valid_doc())
    assert res.inserted_id == "recipe-ok"


def test_missing_name_rejected(mongo_db):
    doc = _valid_doc(_id="no-name")
    del doc["name"]
    with pytest.raises(WriteError):
        mongo_db[RECIPES].insert_one(doc)


def test_non_positive_servings_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[RECIPES].insert_one(_valid_doc(_id="bad-servings", servings=0))


def test_wrong_type_servings_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[RECIPES].insert_one(_valid_doc(_id="str-servings", servings="two"))


def test_ingredient_without_name_rejected(mongo_db):
    bad = [{"quantity": 1.0, "calories": 10}]
    with pytest.raises(WriteError):
        mongo_db[RECIPES].insert_one(_valid_doc(_id="bad-ingredient", ingredients=bad))
