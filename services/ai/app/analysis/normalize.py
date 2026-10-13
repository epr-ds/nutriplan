"""Normalize a model's raw estimate onto the application's nutrition (AIA-302).

The model's :class:`~app.analysis.draft.NutritionEstimateDraft` is advisory text: it may carry
implausible negatives, omit nutrients it could not infer, or report a confidence outside ``[0, 1]``.
These pure functions turn it into a trustworthy :class:`~app.analysis.result.AnalyzedNutrition`
(clamping negatives, preserving "unknown" as ``None``, collapsing a fully empty estimate to
``None``) and carry the low-confidence decision that AC3 surfaces as a warning.
"""

from __future__ import annotations

from app.analysis.draft import NutritionEstimateDraft
from app.analysis.result import AnalyzedNutrition

_NUTRIENTS = ("calories", "protein", "carbs", "fat", "sugar")


def normalize_estimate(draft: NutritionEstimateDraft) -> AnalyzedNutrition | None:
    """Project a draft onto :class:`AnalyzedNutrition`, or ``None`` when nothing was estimated.

    Each known nutrient is clamped to be non-negative; an unknown one stays ``None`` (distinct
    from a measured zero). When the model estimated no nutrient at all, the whole estimate is
    ``None``.
    """
    values = {name: _non_negative(getattr(draft, name)) for name in _NUTRIENTS}
    if all(value is None for value in values.values()):
        return None
    return AnalyzedNutrition(**values)


def clamp_confidence(value: float | None) -> float | None:
    """Clamp a self-reported confidence into ``[0, 1]``; ``None`` (unrated) passes through."""
    if value is None:
        return None
    return min(1.0, max(0.0, value))


def is_low_confidence(
    *,
    confidence: float | None,
    nutrition: AnalyzedNutrition | None,
    threshold: float,
) -> bool:
    """Decide whether an estimate is low-confidence and should be flagged (AC3).

    An estimate is low-confidence when nothing could be estimated at all, or when the model's own
    (clamped) confidence falls below ``threshold``. An estimate the model left unrated but did
    produce is taken at face value.
    """
    if nutrition is None:
        return True
    return confidence is not None and confidence < threshold


def _non_negative(value: int | None) -> int | None:
    if value is None:
        return None
    return value if value >= 0 else 0
