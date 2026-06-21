"""Persistence for the MealPlan aggregate."""

from __future__ import annotations

from pymongo.collection import Collection

from app.db.mongo import meal_plans
from app.domain.meal_plan import MealPlan


class MealPlanRepository:
    """Stores and retrieves :class:`MealPlan` aggregates. Reads are always owner-scoped."""

    def __init__(self, collection: Collection | None = None) -> None:
        self._coll = collection if collection is not None else meal_plans()

    def insert(self, plan: MealPlan) -> MealPlan:
        self._coll.insert_one(plan.to_document())
        return plan

    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        doc = self._coll.find_one({"_id": plan_id, "userId": user_id})
        return MealPlan.from_document(doc) if doc else None
