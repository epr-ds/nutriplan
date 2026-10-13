"""Unit tests for normalizing a model's nutrition estimate (AIA-302).

The estimator asks the model for a :class:`NutritionEstimateDraft` and then *normalizes* it onto the
application's :class:`AnalyzedNutrition`: implausible negatives are clamped, a fully empty estimate
collapses to ``None`` ("nothing could be estimated"), and a self-reported confidence is clamped into
``[0, 1]``. These pure helpers carry the low-confidence decision that AC3 surfaces as a warning.
"""

from __future__ import annotations

from app.analysis.draft import NutritionEstimateDraft
from app.analysis.normalize import (
    clamp_confidence,
    is_low_confidence,
    normalize_estimate,
)
from app.analysis.result import AnalyzedNutrition


def test_normalizes_a_full_estimate() -> None:
    draft = NutritionEstimateDraft(calories=500, protein=20, carbs=60, fat=18, sugar=12)

    assert normalize_estimate(draft) == AnalyzedNutrition(
        calories=500, protein=20, carbs=60, fat=18, sugar=12
    )


def test_clamps_negative_nutrients_to_zero() -> None:
    draft = NutritionEstimateDraft(calories=-50, protein=-1, carbs=60)

    nutrition = normalize_estimate(draft)

    assert nutrition is not None
    assert nutrition.calories == 0
    assert nutrition.protein == 0
    assert nutrition.carbs == 60


def test_keeps_unknown_nutrients_as_none() -> None:
    # A partial estimate (only calories) keeps the rest unknown rather than inventing zeros.
    nutrition = normalize_estimate(NutritionEstimateDraft(calories=400))

    assert nutrition == AnalyzedNutrition(calories=400)
    assert nutrition.protein is None


def test_empty_estimate_collapses_to_none() -> None:
    assert normalize_estimate(NutritionEstimateDraft()) is None


def test_clamp_confidence_bounds_to_unit_interval() -> None:
    assert clamp_confidence(1.4) == 1.0
    assert clamp_confidence(-0.2) == 0.0
    assert clamp_confidence(0.6) == 0.6
    assert clamp_confidence(None) is None


def test_low_confidence_when_self_reported_below_threshold() -> None:
    nutrition = AnalyzedNutrition(calories=500)

    assert is_low_confidence(confidence=0.3, nutrition=nutrition, threshold=0.5) is True
    assert is_low_confidence(confidence=0.8, nutrition=nutrition, threshold=0.5) is False


def test_low_confidence_when_nothing_was_estimated() -> None:
    # No nutrition at all is inherently low confidence, even without a self-reported score.
    assert is_low_confidence(confidence=None, nutrition=None, threshold=0.5) is True


def test_not_low_confidence_when_estimate_present_and_unrated() -> None:
    assert (
        is_low_confidence(confidence=None, nutrition=AnalyzedNutrition(calories=500), threshold=0.5)
        is False
    )
