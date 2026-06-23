"""Deterministic nutritional-alignment scoring for the AI service (AIA-106).

Given a recipe or plan, its calorie/macro targets, and a user's hard preferences, this
package produces a :class:`~app.scoring.types.NutritionalAlignment` -- an overall score
plus a per-nutrient breakdown and any preference violations. It is pure and unit-tested
(no LLM, no I/O), so it is reused wherever alignment is needed: ranking recommendations
(AIA-201/204), grading nutrition estimates (AIA-302), and the offline eval harness
(AIA-701).
"""

from app.scoring.scorer import AlignmentScorer, score_alignment
from app.scoring.types import (
    AlignmentComponent,
    AlignmentWeights,
    NutrientProfile,
    NutrientTargets,
    NutritionalAlignment,
    Preferences,
    ScoringCandidate,
)

__all__ = [
    "AlignmentComponent",
    "AlignmentScorer",
    "AlignmentWeights",
    "NutritionalAlignment",
    "NutrientProfile",
    "NutrientTargets",
    "Preferences",
    "ScoringCandidate",
    "score_alignment",
]
