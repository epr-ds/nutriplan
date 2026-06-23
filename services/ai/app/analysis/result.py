"""What the meal-analysis use case produces (AIA-301).

A :class:`MealAnalysis` is the application-level result the ``/ai/analyze-meal`` route projects onto
the contract's ``NutritionalAnalysisResponse``. It is free of any HTTP/pydantic concern. AIA-301
ships the transport seam, so the result is empty (no nutrition, no warnings) until AIA-302 adds
estimation; every field therefore has a benign default.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AnalyzedNutrition:
    """Estimated per-meal nutrition. A ``None`` nutrient means "unknown", distinct from zero."""

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


@dataclass(frozen=True, slots=True)
class MealAnalysis:
    """The analysis of a described meal: its nutrition plus any advisory warnings.

    ``nutrition`` is ``None`` when nothing could be estimated; ``warnings`` carries human-readable
    advisories (allergens, implausible values, low confidence) and is empty when there are none.
    """

    nutrition: AnalyzedNutrition | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
