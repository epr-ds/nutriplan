"""Application inputs for the meal-analysis use case (AIA-301).

These are the vocabulary the analysis service consumes. They live in the application layer (not the
API layer) so the service never imports HTTP/pydantic concerns: the ``/ai/analyze-meal`` route maps
its validated request onto a :class:`MealAnalysisCommand`, mirroring how the recommendation route
builds a ``RecommendationCommand``. A caller always supplies a free-text ``description`` and may add
structured ``ingredients`` (with optional per-ingredient nutrition) to make the estimate sharper.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MealIngredient:
    """One ingredient line of a meal to analyze; nutrition fields are optional hints.

    A ``None`` nutrient means "unknown" (the estimator in AIA-302 should infer it), kept distinct
    from a measured zero. Collections that hold these stay tuples so the command is hashable.
    """

    name: str
    quantity: float | None = None
    unit: str | None = None
    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


@dataclass(frozen=True, slots=True)
class MealAnalysisCommand:
    """Everything the analysis use case needs: a description, optionally plus structured items."""

    description: str
    ingredients: tuple[MealIngredient, ...] = field(default_factory=tuple)
