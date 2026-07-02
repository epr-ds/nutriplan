"""Application-layer ports (interfaces the use cases depend on, adapters implement)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.meal_plan import MealPlanSnapshot


@runtime_checkable
class MealPlanProvider(Protocol):
    """Resolves an owned meal plan from the Dietary service (anti-corruption boundary).

    Implementations forward the caller's bearer token so Dietary performs the ownership check;
    a plan that is missing or not owned resolves to ``None``. Transport/upstream failures raise
    :class:`~app.domain.errors.MealPlanUnavailableError`.
    """

    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None: ...
