"""Seed data for tests that run against a real MongoDB (DPL-701).

The harness fixtures in ``conftest.py`` (``seeded_recipes``, ``seeded_plan``) use these builders,
and any test (repository, API, provider contract or integration) can call them directly on the
``mongo_db`` database. Everything is written through the service's own code paths -- the reference
catalog upsert (``app.db.seed``), the meal-plan aggregate and ``compute_meal_nutrition`` -- so the
documents are exactly what the service would store, and the collections' ``$jsonSchema``
validators accept them.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from pymongo.database import Database

from app.db.mongo import meal_plans, recipes
from app.db.seed import SEED_RECIPES, seed_recipes
from app.domain.meal_plan import MacroTargets, MealPlan, MealType
from app.domain.nutrition import compute_meal_nutrition
from app.domain.recipe import Recipe
from app.repositories.mongo_meal_plan_repository import MongoMealPlanRepository

#: The owner of the seeded plan; API tests authenticate as this user.
SEED_USER_ID = "harness-user"

#: The seeded plan's week: 2026-10-01 to 2026-10-07, 7 days.
SEED_START = date(2026, 10, 1)
SEED_END = date(2026, 10, 7)

#: The meal types the seeded meals take, in order (one meal per day from the first day).
SEED_MEAL_TYPES = (MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER)


def seed_catalog(db: Database) -> list[Recipe]:
    """Load the reference recipe catalog into *db* (idempotent) and return its recipes."""
    seed_recipes(recipes(db))
    return list(SEED_RECIPES)


def seed_plan(
    db: Database,
    catalog: Sequence[Recipe],
    *,
    user_id: str = SEED_USER_ID,
    name: str = "Harness week",
    daily_calorie_target: int = 2000,
    meal_count: int = len(SEED_MEAL_TYPES),
) -> MealPlan:
    """Store a one-week draft plan for *user_id* with *meal_count* meals from *catalog*.

    Meal *i* is the *i*-th catalog recipe, one serving, on day *i*, with the meal types cycling
    through :data:`SEED_MEAL_TYPES`; its nutrition is computed like the service does.
    """
    if meal_count > len(catalog):
        raise ValueError(f"meal_count={meal_count} needs at least that many recipes")
    plan = MealPlan.create(
        user_id=user_id,
        name=name,
        start_date=SEED_START,
        end_date=SEED_END,
        daily_calorie_target=daily_calorie_target,
        macro_targets=MacroTargets(protein_grams=120),
    )
    for index, recipe in enumerate(catalog[:meal_count]):
        plan.add_meal(
            meal_type=SEED_MEAL_TYPES[index % len(SEED_MEAL_TYPES)],
            recipe_id=recipe.id,
            servings=1,
            day_index=index,
            nutritional_info=compute_meal_nutrition(recipe, 1),
        )
    MongoMealPlanRepository(meal_plans(db)).add(plan)
    return plan
