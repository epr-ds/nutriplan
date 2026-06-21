"""Repository ports for the Dietary Planning domain.

Following the Dependency Inversion Principle / Ports & Adapters, the domain and application layers
depend on this abstract :class:`MealPlanRepository` rather than on any concrete database. The
MongoDB adapter lives in :mod:`app.repositories.mongo_meal_plan_repository`; tests substitute an
in-memory implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.meal_plan import MealPlan


class MealPlanRepository(ABC):
    """Persistence boundary for the :class:`~app.domain.meal_plan.MealPlan` aggregate."""

    @abstractmethod
    def add(self, plan: MealPlan) -> None:
        """Persist a newly created aggregate."""

    @abstractmethod
    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        """Return the caller-owned plan, or ``None`` if it does not exist for this user."""
