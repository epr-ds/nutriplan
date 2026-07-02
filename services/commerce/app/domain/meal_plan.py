"""Domain view of a Dietary meal plan (the anti-corruption layer's translated shape).

Commerce does not depend on the Dietary wire model. The :class:`MealPlanProvider` port returns
these small value objects — just enough of a plan to build order line items — so the rest of the
domain never sees Dietary's schema. Pricing is deliberately absent here: order items start at zero
and are priced by the engine in COM-103.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class PlannedMeal:
    """One meal of a plan, reduced to what an order line needs.

    ``recipe_name`` is optional because plan *reads* in Dietary do not expand the recipe; when it is
    absent the order-item name falls back to a label derived from ``meal_type``.
    """

    meal_type: str
    servings: Decimal
    recipe_name: str | None = None


@dataclass(frozen=True)
class MealPlanSnapshot:
    """An owned meal plan resolved from Dietary, ready to be turned into order items."""

    plan_id: str
    meals: list[PlannedMeal] = field(default_factory=list)
