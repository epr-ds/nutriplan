"""What the meal-analysis use case produces (AIA-301, AIA-302).

A :class:`MealAnalysis` is the application-level result the ``/ai/analyze-meal`` route projects onto
the contract's ``NutritionalAnalysisResponse``. It is free of any HTTP/pydantic concern. AIA-301
shipped the transport seam (every field has a benign default); AIA-302 fills it with an estimated
nutrition, an alignment scored against a balanced-meal reference, and any advisory warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.scoring.types import NutritionalAlignment


@dataclass(frozen=True, slots=True)
class AnalyzedNutrition:
    """Estimated per-meal nutrition. A ``None`` nutrient means "unknown", distinct from zero."""

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


@dataclass(frozen=True, slots=True)
class MealAlignment:
    """How balanced an estimated meal is against a reference, plus a human-readable summary.

    Wraps the deterministic AIA-106 :class:`~app.scoring.types.NutritionalAlignment` so the API can
    project the contract's compact ``score`` + ``details`` without the analysis layer importing
    pydantic/HTTP concerns.
    """

    alignment: NutritionalAlignment
    details: str

    @property
    def score(self) -> float:
        """The overall alignment score (0-1)."""
        return self.alignment.score

    @property
    def percentage(self) -> float:
        """The overall alignment score as a 0-100 percentage."""
        return self.alignment.percentage


@dataclass(frozen=True, slots=True)
class MealAnalysis:
    """The analysis of a described meal: its nutrition, its alignment, and any warnings.

    ``nutrition`` is ``None`` when nothing could be estimated; ``alignment`` is ``None`` when
    there is no nutrition to score; ``warnings`` carries human-readable advisories (low confidence,
    allergens, and over/under-target bounds) and is empty when there are none; ``disclaimer`` is the
    AIA-505 medical disclaimer attached to every response.
    """

    nutrition: AnalyzedNutrition | None = None
    alignment: MealAlignment | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    disclaimer: str | None = None
