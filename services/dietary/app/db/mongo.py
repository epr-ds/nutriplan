"""MongoDB wiring for the Dietary service.

Holds the cached PyMongo client, the ``meal_plans`` collection accessor, and
``ensure_meal_plans_collection`` which idempotently installs the write-time ``$jsonSchema``
validator and the indexes required by DPL-101 (userId, status, and the start/end date range).
"""

from __future__ import annotations

from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import settings

MEAL_PLANS = "meal_plans"

# Applied to every write on meal_plans: enforces required fields, BSON types, and enum domains
# (DPL-101 "schema validation on write"). Dates and timestamps are stored as ISO-8601 strings,
# whose lexicographic order is chronological — so the date-range index stays range-queryable.
MEAL_PLAN_VALIDATOR: dict = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "userId",
            "name",
            "startDate",
            "endDate",
            "dailyCalorieTarget",
            "status",
            "meals",
            "createdAt",
        ],
        "properties": {
            "_id": {"bsonType": "string"},
            "userId": {"bsonType": "string"},
            "name": {"bsonType": "string", "minLength": 1},
            "startDate": {"bsonType": "string"},
            "endDate": {"bsonType": "string"},
            "dailyCalorieTarget": {"bsonType": "int"},
            "status": {"enum": ["draft", "active", "completed", "saved"]},
            "dietaryType": {"enum": ["omnivore", "vegetarian", "vegan", "keto", "paleo"]},
            "macroTargets": {"bsonType": "object"},
            "meals": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["id", "mealType", "recipeId", "servings"],
                    "properties": {
                        "id": {"bsonType": "string"},
                        "mealType": {"enum": ["breakfast", "lunch", "dinner", "snack"]},
                        "recipeId": {"bsonType": "string"},
                        "servings": {"bsonType": ["double", "int"]},
                        "dayIndex": {"bsonType": "int"},
                        "nutritionalInfo": {"bsonType": "object"},
                    },
                },
            },
            "createdAt": {"bsonType": "string"},
            "updatedAt": {"bsonType": "string"},
        },
    }
}


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(
        settings.mongo_url,
        serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
        uuidRepresentation="standard",
    )


def get_db() -> Database:
    return get_client()[settings.mongo_db]


def meal_plans(db: Database | None = None) -> Collection:
    return (db if db is not None else get_db())[MEAL_PLANS]


def ensure_meal_plans_collection(db: Database) -> Collection:
    """Idempotently install the meal_plans validator and indexes (safe to call on every boot)."""
    if MEAL_PLANS in db.list_collection_names():
        db.command("collMod", MEAL_PLANS, validator=MEAL_PLAN_VALIDATOR)
    else:
        db.create_collection(MEAL_PLANS, validator=MEAL_PLAN_VALIDATOR)

    coll = db[MEAL_PLANS]
    coll.create_index([("userId", ASCENDING)], name="userId_1")
    coll.create_index([("userId", ASCENDING), ("status", ASCENDING)], name="userId_status")
    coll.create_index(
        [("userId", ASCENDING), ("startDate", ASCENDING), ("endDate", ASCENDING)],
        name="userId_dateRange",
    )
    return coll
