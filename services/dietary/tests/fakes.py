"""Reusable test doubles for the Dietary service."""

from __future__ import annotations

from app.domain.meal_plan import MealPlan
from app.domain.repositories import MealPlanRepository


class InMemoryMealPlanRepository(MealPlanRepository):
    """A dict-backed :class:`MealPlanRepository` for fast, Mongo-free unit tests."""

    def __init__(self) -> None:
        self.saved: dict[str, MealPlan] = {}

    def add(self, plan: MealPlan) -> None:
        self.saved[plan.id] = plan

    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        plan = self.saved.get(plan_id)
        return plan if plan is not None and plan.user_id == user_id else None
