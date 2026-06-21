"""Reusable test doubles for the Dietary service."""

from __future__ import annotations

from app.domain.meal_plan import MealPlan, MealPlanStatus
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

    def update(self, plan: MealPlan) -> None:
        existing = self.saved.get(plan.id)
        if existing is not None and existing.user_id == plan.user_id:
            self.saved[plan.id] = plan

    def list_for_user(
        self,
        user_id: str,
        *,
        status: MealPlanStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MealPlan]:
        plans = [p for p in self.saved.values() if p.user_id == user_id]
        if status is not None:
            want = status.value if isinstance(status, MealPlanStatus) else status
            plans = [p for p in plans if p.status == want]
        # Newest first, with a stable id tiebreaker — mirrors the Mongo adapter's ordering.
        plans.sort(key=lambda p: (p.created_at, p.id), reverse=True)
        return plans[skip : skip + limit]
