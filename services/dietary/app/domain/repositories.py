"""Repository ports for the Dietary Planning domain.

Following the Dependency Inversion Principle / Ports & Adapters, the domain and application layers
depend on this abstract :class:`MealPlanRepository` rather than on any concrete database. The
MongoDB adapter lives in :mod:`app.repositories.mongo_meal_plan_repository`; tests substitute an
in-memory implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.meal_plan import MealPlan, MealPlanStatus
from app.domain.recipe import Recipe


class MealPlanRepository(ABC):
    """Persistence boundary for the :class:`~app.domain.meal_plan.MealPlan` aggregate."""

    @abstractmethod
    def add(self, plan: MealPlan) -> None:
        """Persist a newly created aggregate."""

    @abstractmethod
    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        """Return the caller-owned plan, or ``None`` if it does not exist for this user."""

    @abstractmethod
    def update(self, plan: MealPlan) -> None:
        """Persist mutations to an existing aggregate, scoped to ``plan.user_id``.

        Only the owner's document is ever written, so a plan can never be modified on behalf of a
        different user even if a stale/forged aggregate is supplied.
        """

    @abstractmethod
    def list_for_user(
        self,
        user_id: str,
        *,
        status: MealPlanStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MealPlan]:
        """Return the caller's plans, newest first, optionally filtered by *status*.

        ``skip``/``limit`` provide offset pagination; the result is always owner-scoped.
        """


class RecipeRepository(ABC):
    """Persistence boundary for the :class:`~app.domain.recipe.Recipe` aggregate.

    Recipes are a shared catalog (not owner-scoped), so reads are keyed by recipe id alone.
    """

    @abstractmethod
    def add(self, recipe: Recipe) -> None:
        """Persist a newly created recipe."""

    @abstractmethod
    def get(self, recipe_id: str) -> Recipe | None:
        """Return the recipe with *recipe_id*, or ``None`` if it does not exist."""
