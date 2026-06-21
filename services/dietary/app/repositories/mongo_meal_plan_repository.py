"""MongoDB adapter for the MealPlan repository port (DPL-101/102/103)."""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from app.db.mongo import meal_plans
from app.domain.meal_plan import MealPlan, MealPlanStatus
from app.domain.repositories import MealPlanRepository


class MongoMealPlanRepository(MealPlanRepository):
    """Stores and retrieves :class:`MealPlan` aggregates in MongoDB. Reads are owner-scoped."""

    def __init__(self, collection: Collection | None = None) -> None:
        self._coll = collection if collection is not None else meal_plans()

    def add(self, plan: MealPlan) -> None:
        self._coll.insert_one(plan.to_document())

    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        doc = self._coll.find_one({"_id": plan_id, "userId": user_id})
        return MealPlan.from_document(doc) if doc else None

    def list_for_user(
        self,
        user_id: str,
        *,
        status: MealPlanStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MealPlan]:
        query: dict[str, str] = {"userId": user_id}
        if status is not None:
            query["status"] = status.value if isinstance(status, MealPlanStatus) else status
        cursor = (
            self._coll.find(query)
            .sort([("createdAt", DESCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        return [MealPlan.from_document(doc) for doc in cursor]
