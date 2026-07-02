"""HTTP adapter implementing :class:`~app.application.ports.MealPlanProvider` against Dietary.

This is the first inter-service call in the platform and forms an anti-corruption layer around the
Dietary meal-plan API: it forwards the caller's bearer token (so Dietary enforces ownership), maps a
``404`` to ``None`` (missing or not-owned), and normalises every transport/upstream failure to
:class:`~app.domain.errors.MealPlanUnavailableError`. A synchronous ``httpx.Client`` keeps the whole
request path consistent with the service's sync SQLAlchemy stack; a ``transport`` can be injected so
the mapping is unit-testable without a live Dietary.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.domain.errors import MealPlanUnavailableError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal


class HttpMealPlanProvider:
    """Fetches meal plans from the Dietary service over HTTP."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None:
        headers = {"Authorization": f"Bearer {bearer_token}"}
        try:
            with httpx.Client(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.get(f"/meal-plans/{plan_id}", headers=headers)
        except httpx.HTTPError as exc:
            raise MealPlanUnavailableError(f"dietary request failed: {exc}") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise MealPlanUnavailableError(f"dietary returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise MealPlanUnavailableError("dietary returned a non-JSON body") from exc
        return self._to_snapshot(plan_id, payload)

    @staticmethod
    def _to_snapshot(plan_id: str, payload: dict[str, Any]) -> MealPlanSnapshot:
        meals: list[PlannedMeal] = []
        for raw in payload.get("meals") or []:
            recipe = raw.get("recipe")
            recipe_name = recipe.get("name") if isinstance(recipe, dict) else None
            meals.append(
                PlannedMeal(
                    meal_type=str(raw.get("mealType", "")),
                    servings=_to_decimal(raw.get("servings")),
                    recipe_name=recipe_name,
                )
            )
        return MealPlanSnapshot(plan_id=plan_id, meals=meals)


def _to_decimal(value: Any) -> Decimal:
    """Coerce a JSON ``number`` servings value to Decimal, defaulting to 1 when absent/invalid."""
    if value is None:
        return Decimal(1)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(1)
