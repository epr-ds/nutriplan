"""The recommendation result vocabulary (AIA-203).

A ``RecommendedRecipe`` is what the recommendation use case ultimately produces, regardless of where
it came from: it is either **linked** to a real catalogue recipe (``source = catalogue``) or
**synthesized** from the model's own output (``source = synthesized``). Either way it is a complete,
usable recipe -- ingredients, steps, and nutrition -- so the API layer can project it straight onto
the ``RecipeResponse`` wire shape. These are immutable application value objects, deliberately free
of any HTTP/pydantic concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RecipeSource(StrEnum):
    """Where a recommended recipe came from."""

    CATALOGUE = "catalogue"
    SYNTHESIZED = "synthesized"


@dataclass(frozen=True, slots=True)
class RecommendedIngredient:
    """A single ingredient line of a recommended recipe."""

    name: str
    quantity: float | None = None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendedNutrition:
    """Per-serving nutrition for a recommended recipe (calories are always present)."""

    calories: int
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


@dataclass(frozen=True, slots=True)
class RecommendedRecipe:
    """A complete, usable recipe surfaced by the recommendation use case."""

    id: str
    name: str
    servings: int
    ingredients: tuple[RecommendedIngredient, ...]
    instructions: tuple[str, ...]
    nutrition: RecommendedNutrition
    source: RecipeSource
    description: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    dietary_types: tuple[str, ...] = field(default_factory=tuple)
