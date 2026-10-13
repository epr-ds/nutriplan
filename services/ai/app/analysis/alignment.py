"""Score an estimated meal against a balanced single-meal reference (AIA-302, AC2).

The analyze-meal request carries no user targets, so there is nothing user-specific to align to.
Instead this reuses the deterministic AIA-106 :class:`~app.scoring.scorer.AlignmentScorer` to say
how balanced the estimate is against a configurable single-meal :class:`MealReference` (roughly a
third of a 2000 kcal day at a ~20/50/30 protein/carb/fat split). Only the nutrients the model
actually estimated are scored -- an unknown nutrient is left untargeted rather than counted as a
miss -- so a partial estimate is judged on what it does say. It is pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.result import AnalyzedNutrition, MealAlignment
from app.scoring.scorer import AlignmentScorer
from app.scoring.types import (
    NUTRIENTS,
    NutrientProfile,
    NutrientTargets,
    NutritionalAlignment,
    ScoringCandidate,
)


@dataclass(frozen=True, slots=True)
class MealReference:
    """Calorie/macro targets for one balanced meal; a ``None`` leaves a nutrient untargeted.

    Defaults approximate a balanced single meal (~1/3 of a 2000 kcal day, ~20/50/30 protein/carb/fat
    by energy). Injected into :class:`MealAligner`, so the policy is explicit and overridable.
    """

    calories: float | None = 650
    protein: float | None = 30
    carbs: float | None = 80
    fat: float | None = 22
    sugar: float | None = 15


class MealAligner:
    """Score an estimated meal's nutrition against a single-meal reference (reusing AIA-106)."""

    def __init__(
        self,
        reference: MealReference | None = None,
        scorer: AlignmentScorer | None = None,
    ) -> None:
        self._reference = reference or MealReference()
        self._scorer = scorer or AlignmentScorer()

    @property
    def reference(self) -> MealReference:
        """The balanced-meal reference this aligner scores against (reused for bounds warnings)."""
        return self._reference

    def align(self, nutrition: AnalyzedNutrition | None) -> MealAlignment | None:
        """Return the meal's alignment, or ``None`` when there is nothing to score."""
        if nutrition is None:
            return None
        targets = self._targets(nutrition)
        if not _has_target(targets):
            return None
        candidate = ScoringCandidate(
            nutrition=NutrientProfile(
                calories=nutrition.calories,
                protein=nutrition.protein,
                carbs=nutrition.carbs,
                fat=nutrition.fat,
                sugar=nutrition.sugar,
            )
        )
        alignment = self._scorer.score(candidate, targets)
        return MealAlignment(alignment=alignment, details=_details(alignment, nutrition))

    def _targets(self, nutrition: AnalyzedNutrition) -> NutrientTargets:
        # Mask the reference to the nutrients the meal actually estimated, so unknowns drop out of
        # the score (an unknown actual against a real target would otherwise score as a miss).
        return NutrientTargets(
            **{
                name: (
                    getattr(self._reference, name) if getattr(nutrition, name) is not None else None
                )
                for name in NUTRIENTS
            }
        )


def _has_target(targets: NutrientTargets) -> bool:
    return any(getattr(targets, name) is not None for name in NUTRIENTS)


def _details(alignment: NutritionalAlignment, nutrition: AnalyzedNutrition) -> str:
    if nutrition.calories is not None:
        energy = f"about {nutrition.calories} kcal"
    else:
        energy = "an unspecified number of calories"
    return f"This meal provides {energy} and aligns {alignment.percentage:g}% with a balanced meal."
