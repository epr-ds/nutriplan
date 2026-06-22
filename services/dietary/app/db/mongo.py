"""MongoDB wiring for the Dietary service.

Holds the cached PyMongo client, the ``meal_plans`` and ``recipes`` collection accessors, and the
``ensure_*_collection`` helpers which idempotently install each write-time ``$jsonSchema`` validator
and indexes: ``meal_plans`` (DPL-101: userId, status, start/end date range) and ``recipes``
(DPL-201: ingredient name + per-serving macro filters).
"""

from __future__ import annotations

from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import settings

MEAL_PLANS = "meal_plans"
RECIPES = "recipes"

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

# Applied to every write on recipes (DPL-201): enforces the Recipe/Ingredient/NutritionalInfo
# shape from contracts/dietary.openapi.yaml. ``servings`` must be a positive int (per-serving
# nutrition is only meaningful for >= 1 serving) and every ingredient must carry a name.
RECIPE_VALIDATOR: dict = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "name", "servings", "ingredients", "createdAt"],
        "properties": {
            "_id": {"bsonType": "string"},
            "name": {"bsonType": "string", "minLength": 1},
            "description": {"bsonType": "string"},
            "ingredients": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"bsonType": "string", "minLength": 1},
                        "quantity": {"bsonType": ["double", "int"]},
                        "unit": {"bsonType": "string"},
                        "calories": {"bsonType": "int"},
                        "protein": {"bsonType": ["double", "int"]},
                        "carbs": {"bsonType": ["double", "int"]},
                        "fat": {"bsonType": ["double", "int"]},
                        "sugar": {"bsonType": ["double", "int"]},
                    },
                },
            },
            "instructions": {"bsonType": "array", "items": {"bsonType": "string"}},
            "prepTime": {"bsonType": "int"},
            "cookTime": {"bsonType": "int"},
            "servings": {"bsonType": "int", "minimum": 1},
            "imageUrl": {"bsonType": "string"},
            "dietaryTypes": {
                "bsonType": "array",
                "items": {"enum": ["omnivore", "vegetarian", "vegan", "keto", "paleo"]},
            },
            "nutritionalInfo": {
                "bsonType": "object",
                "properties": {
                    "calories": {"bsonType": "int"},
                    "protein": {"bsonType": ["double", "int"]},
                    "carbs": {"bsonType": ["double", "int"]},
                    "fat": {"bsonType": ["double", "int"]},
                    "sugar": {"bsonType": ["double", "int"]},
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


def recipes(db: Database | None = None) -> Collection:
    return (db if db is not None else get_db())[RECIPES]


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


def ensure_recipes_collection(db: Database) -> Collection:
    """Idempotently install the recipes validator and the ingredient + macro filter indexes.

    DPL-201 requires the catalog to be queryable by ingredient and by macro nutrient, so a
    multikey index covers ``ingredients.name`` and one index per per-serving macro covers the
    nutritional filters. DPL-202 adds a multikey index on ``dietaryTypes`` for the diet filter.
    Safe to call on every boot.
    """
    if RECIPES in db.list_collection_names():
        db.command("collMod", RECIPES, validator=RECIPE_VALIDATOR)
    else:
        db.create_collection(RECIPES, validator=RECIPE_VALIDATOR)

    coll = db[RECIPES]
    coll.create_index([("ingredients.name", ASCENDING)], name="ingredientName")
    coll.create_index([("nutritionalInfo.calories", ASCENDING)], name="nutrition_calories")
    coll.create_index([("nutritionalInfo.protein", ASCENDING)], name="nutrition_protein")
    coll.create_index([("nutritionalInfo.carbs", ASCENDING)], name="nutrition_carbs")
    coll.create_index([("nutritionalInfo.fat", ASCENDING)], name="nutrition_fat")
    coll.create_index([("dietaryTypes", ASCENDING)], name="dietaryTypes")
    return coll
