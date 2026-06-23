"""Deterministic nutritional-alignment scoring (AIA-106).

Pure arithmetic, no I/O and no LLM: the same inputs always yield the same
:class:`~app.scoring.types.NutritionalAlignment`, which is what makes it unit-testable
(AC2) and safe to reuse for ranking recommendations (AIA-201/204), nutrition estimates
(AIA-302), and the offline eval harness (AIA-701).

How the score is built:

- **Per-nutrient closeness.** For each *targeted* nutrient, relative deviation
  ``|actual - target| / target`` is turned into a ``[0, 1]`` closeness that is ``1`` on the
  target and falls to ``0`` once the deviation reaches ``tolerance`` (default: off by 100%).
  An unknown actual against a real target scores ``0`` -- it cannot be confirmed aligned.
- **Weighted nutrition score.** Closeness values are averaged using
  :class:`~app.scoring.types.AlignmentWeights`, renormalized over whichever nutrients are
  actually targeted (an untargeted nutrient simply drops out).
- **Preference gate.** Required diets and excluded ingredients are hard constraints: any
  violation zeroes the overall ``score`` (the item should not be recommended) while the
  nutrition score is retained for transparency.
- **Threshold.** ``aligned`` is ``True`` when there are no violations and the score clears
  the configured threshold.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.scoring.types import (
    NUTRIENTS,
    AlignmentComponent,
    AlignmentWeights,
    NutrientTargets,
    NutritionalAlignment,
    Preferences,
    ScoringCandidate,
)

_QUANTUM = Decimal("0.0001")


def _round4(value: float) -> float:
    """Round half-up to four places, so scores compare exactly in tests."""
    return float(Decimal(str(value)).quantize(_QUANTUM, rounding=ROUND_HALF_UP))


class AlignmentScorer:
    """Score a candidate against calorie/macro targets and hard preferences.

    Weights, the deviation ``tolerance``, and the ``aligned`` ``threshold`` are injected so
    the policy is configurable and explicit; the defaults are sensible for recipe scoring.
    """

    def __init__(
        self,
        *,
        weights: AlignmentWeights | None = None,
        tolerance: float = 1.0,
        threshold: float = 0.7,
    ) -> None:
        if tolerance <= 0:
            raise ValueError("tolerance must be greater than 0")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self._weights = weights or AlignmentWeights()
        self._tolerance = tolerance
        self._threshold = threshold

    def score(
        self,
        candidate: ScoringCandidate,
        targets: NutrientTargets,
        preferences: Preferences | None = None,
    ) -> NutritionalAlignment:
        """Return the alignment of ``candidate`` with ``targets`` and ``preferences``."""
        preferences = preferences or Preferences()
        components: list[AlignmentComponent] = []
        weighted_sum = 0.0
        weight_total = 0.0

        for nutrient in NUTRIENTS:
            target = getattr(targets, nutrient)
            if target is None:
                continue
            actual = getattr(candidate.nutrition, nutrient)
            closeness, detail = self._closeness(actual, float(target))
            weight = getattr(self._weights, nutrient)
            components.append(
                AlignmentComponent(
                    name=nutrient,
                    score=closeness,
                    weight=weight,
                    target=target,
                    actual=actual,
                    detail=detail,
                )
            )
            weighted_sum += closeness * weight
            weight_total += weight

        nutrition_score = _round4(weighted_sum / weight_total) if weight_total > 0 else 1.0

        violations = self._violations(candidate, preferences)
        components.append(
            AlignmentComponent(
                name="preferences",
                score=0.0 if violations else 1.0,
                weight=0.0,
                detail="; ".join(violations) if violations else "all preferences satisfied",
            )
        )

        score = 0.0 if violations else nutrition_score
        return NutritionalAlignment(
            score=_round4(score),
            nutrition_score=nutrition_score,
            aligned=not violations and score >= self._threshold,
            components=tuple(components),
            violations=tuple(violations),
        )

    def _closeness(self, actual: float | None, target: float) -> tuple[float, str]:
        if target <= 0:
            return 1.0, "no positive target"
        if actual is None:
            return 0.0, "actual unknown"
        deviation = abs(actual - target) / target
        closeness = max(0.0, 1.0 - deviation / self._tolerance)
        delta_pct = round((actual - target) / target * 100, 1)
        return _round4(closeness), f"{actual:g} vs target {target:g} (delta {delta_pct:+g}%)"

    @staticmethod
    def _violations(candidate: ScoringCandidate, preferences: Preferences) -> list[str]:
        candidate_diets = {diet.lower() for diet in candidate.diets}
        candidate_ingredients = {item.lower() for item in candidate.ingredients}
        violations: list[str] = []
        for diet in sorted(d.lower() for d in preferences.required_diets):
            if diet not in candidate_diets:
                violations.append(f"not compatible with diet: {diet}")
        for excluded in sorted(e.lower() for e in preferences.excluded_ingredients):
            if excluded in candidate_ingredients:
                violations.append(f"contains excluded ingredient: {excluded}")
        return violations


_DEFAULT_SCORER = AlignmentScorer()


def score_alignment(
    candidate: ScoringCandidate,
    targets: NutrientTargets,
    preferences: Preferences | None = None,
) -> NutritionalAlignment:
    """Score with the default policy; inject an :class:`AlignmentScorer` to customize it."""
    return _DEFAULT_SCORER.score(candidate, targets, preferences)
