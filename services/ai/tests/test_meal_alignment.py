"""Unit tests for scoring a meal estimate against a balanced-meal reference (AIA-302, AC2).

The analyze-meal request carries no user targets, so alignment is computed by reusing the
deterministic AIA-106 :class:`~app.scoring.scorer.AlignmentScorer` against a configurable
single-meal :class:`MealReference`. Only the nutrients that were actually estimated are scored
(unknowns are left untargeted rather than counted as misses), and an empty estimate yields no
alignment at all.
"""

from __future__ import annotations

from app.analysis.alignment import MealAligner, MealReference
from app.analysis.result import AnalyzedNutrition


def test_no_alignment_without_an_estimate() -> None:
    assert MealAligner().align(None) is None


def test_perfect_alignment_against_a_matching_reference() -> None:
    reference = MealReference(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    nutrition = AnalyzedNutrition(calories=500, protein=20, carbs=60, fat=18, sugar=12)

    result = MealAligner(reference=reference).align(nutrition)

    assert result is not None
    assert result.percentage == 100.0


def test_imbalanced_meal_scores_below_a_balanced_reference() -> None:
    reference = MealReference(calories=600, protein=30, carbs=80, fat=20, sugar=15)
    # Double the calories with no macros that match: clearly off a balanced single meal.
    nutrition = AnalyzedNutrition(calories=1200, protein=5, carbs=10, fat=80, sugar=90)

    result = MealAligner(reference=reference).align(nutrition)

    assert result is not None
    assert result.percentage < 50.0


def test_only_estimated_nutrients_are_scored() -> None:
    # A calories-only estimate must not be penalized for the macros the model never gave.
    reference = MealReference(calories=500, protein=30, carbs=80, fat=20, sugar=15)

    result = MealAligner(reference=reference).align(AnalyzedNutrition(calories=500))

    assert result is not None
    assert result.percentage == 100.0
    scored = {c.name for c in result.alignment.components if c.weight > 0}
    assert scored == {"calories"}


def test_details_mentions_the_alignment_percentage() -> None:
    reference = MealReference(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    nutrition = AnalyzedNutrition(calories=500, protein=20, carbs=60, fat=18, sugar=12)

    result = MealAligner(reference=reference).align(nutrition)

    assert result is not None
    assert "100" in result.details
    assert "500" in result.details
