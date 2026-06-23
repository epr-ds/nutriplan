"""Deterministic tests for nutritional-alignment scoring (AIA-106, AC2 + AC3)."""

import pytest

from app.scoring.scorer import AlignmentScorer, score_alignment
from app.scoring.types import (
    AlignmentWeights,
    NutrientProfile,
    NutrientTargets,
    NutritionalAlignment,
    Preferences,
    ScoringCandidate,
)


def _candidate(diets=frozenset(), ingredients=frozenset(), **nutrition) -> ScoringCandidate:
    return ScoringCandidate(
        nutrition=NutrientProfile(**nutrition),
        diets=diets,
        ingredients=ingredients,
    )


def _component(alignment: NutritionalAlignment, name: str):
    return next(c for c in alignment.components if c.name == name)


def test_perfect_match_scores_one_and_is_aligned() -> None:
    targets = NutrientTargets(calories=500, protein=50, carbs=100, fat=20)
    candidate = _candidate(calories=500, protein=50, carbs=100, fat=20)

    result = AlignmentScorer().score(candidate, targets)

    assert result.score == 1.0
    assert result.nutrition_score == 1.0
    assert result.aligned is True
    assert result.violations == ()
    assert result.percentage == 100.0


def test_partial_calorie_deviation_is_linear() -> None:
    result = AlignmentScorer().score(_candidate(calories=550), NutrientTargets(calories=500))

    calories = _component(result, "calories")
    assert calories.score == 0.9  # off by 10% of target under tolerance 1.0
    assert calories.detail == "550 vs target 500 (delta +10%)"
    assert result.nutrition_score == 0.9


def test_over_and_under_are_penalized_symmetrically() -> None:
    scorer = AlignmentScorer()
    over = scorer.score(_candidate(calories=550), NutrientTargets(calories=500))
    under = scorer.score(_candidate(calories=450), NutrientTargets(calories=500))
    assert over.nutrition_score == under.nutrition_score == 0.9


def test_deviation_beyond_tolerance_floors_at_zero() -> None:
    scorer = AlignmentScorer()
    assert scorer.score(_candidate(calories=1000), NutrientTargets(calories=500)).score == 0.0
    assert scorer.score(_candidate(calories=2500), NutrientTargets(calories=500)).score == 0.0


def test_unknown_actual_against_a_target_scores_zero() -> None:
    result = AlignmentScorer().score(_candidate(protein=None), NutrientTargets(protein=50))

    protein = _component(result, "protein")
    assert protein.score == 0.0
    assert protein.detail == "actual unknown"


def test_untargeted_nutrients_are_excluded() -> None:
    result = AlignmentScorer().score(
        _candidate(calories=500, protein=999), NutrientTargets(calories=500)
    )

    names = {c.name for c in result.components}
    assert names == {"calories", "preferences"}  # protein had no target


def test_no_targets_yields_full_nutrition_score() -> None:
    result = AlignmentScorer().score(_candidate(calories=500), NutrientTargets())
    assert result.nutrition_score == 1.0
    assert result.score == 1.0


def test_weights_are_renormalized_over_targeted_nutrients() -> None:
    targets = NutrientTargets(calories=500, carbs=100)
    candidate = _candidate(calories=500, carbs=150)  # calories perfect, carbs off 50%

    result = AlignmentScorer().score(candidate, targets)

    # (1.0*1.0 + 0.5*0.75) / (1.0 + 0.75) == 1.375 / 1.75
    assert result.nutrition_score == 0.7857
    assert result.aligned is True


def test_custom_weights_change_the_blend() -> None:
    scorer = AlignmentScorer(weights=AlignmentWeights(calories=3.0, protein=1.0))
    targets = NutrientTargets(calories=500, protein=50)
    candidate = _candidate(calories=600, protein=50)  # calories 0.8, protein 1.0

    # (0.8*3 + 1.0*1) / 4 == 0.85
    assert scorer.score(candidate, targets).nutrition_score == 0.85


def test_custom_tolerance_tightens_scoring() -> None:
    scorer = AlignmentScorer(tolerance=0.2)
    result = scorer.score(_candidate(calories=550), NutrientTargets(calories=500))
    assert result.nutrition_score == 0.5  # 10% deviation over a 20% tolerance


def test_diet_violation_zeroes_the_score_but_keeps_nutrition() -> None:
    targets = NutrientTargets(calories=500)
    candidate = _candidate(calories=500, diets=frozenset({"vegetarian"}))

    result = AlignmentScorer().score(candidate, targets, Preferences(required_diets={"vegan"}))

    assert result.violations == ("not compatible with diet: vegan",)
    assert result.score == 0.0
    assert result.aligned is False
    assert result.nutrition_score == 1.0  # retained for transparency
    assert _component(result, "preferences").score == 0.0


def test_excluded_ingredient_is_a_violation() -> None:
    candidate = _candidate(calories=500, ingredients=frozenset({"peanut", "rice"}))
    result = AlignmentScorer().score(
        candidate, NutrientTargets(calories=500), Preferences(excluded_ingredients={"peanut"})
    )
    assert result.violations == ("contains excluded ingredient: peanut",)
    assert result.score == 0.0


def test_preference_matching_is_case_insensitive() -> None:
    candidate = _candidate(
        calories=500, diets=frozenset({"VEGAN"}), ingredients=frozenset({"Peanut"})
    )
    satisfied = AlignmentScorer().score(
        candidate, NutrientTargets(calories=500), Preferences(required_diets={"vegan"})
    )
    assert satisfied.violations == ()

    violated = AlignmentScorer().score(
        candidate, NutrientTargets(calories=500), Preferences(excluded_ingredients={"peanut"})
    )
    assert violated.violations == ("contains excluded ingredient: peanut",)


def test_only_missing_required_diets_are_reported() -> None:
    candidate = _candidate(calories=500, diets=frozenset({"vegan"}))
    result = AlignmentScorer().score(
        candidate, NutrientTargets(calories=500), Preferences(required_diets={"vegan", "keto"})
    )
    assert result.violations == ("not compatible with diet: keto",)


def test_satisfied_preferences_pass_the_gate() -> None:
    candidate = _candidate(
        calories=500, diets=frozenset({"vegan", "vegetarian"}), ingredients=frozenset({"tofu"})
    )
    result = AlignmentScorer().score(
        candidate,
        NutrientTargets(calories=500),
        Preferences(required_diets={"vegan"}, excluded_ingredients={"shellfish"}),
    )
    assert result.violations == ()
    assert _component(result, "preferences").score == 1.0
    assert result.score == 1.0


def test_threshold_boundary_is_inclusive() -> None:
    scorer = AlignmentScorer(threshold=0.7)
    at_threshold = scorer.score(_candidate(calories=650), NutrientTargets(calories=500))
    below = scorer.score(_candidate(calories=700), NutrientTargets(calories=500))
    assert at_threshold.nutrition_score == 0.7
    assert at_threshold.aligned is True
    assert below.nutrition_score == 0.6
    assert below.aligned is False


def test_scoring_is_deterministic() -> None:
    targets = NutrientTargets(calories=500, protein=40)
    candidate = _candidate(calories=560, protein=35)
    scorer = AlignmentScorer()
    assert scorer.score(candidate, targets) == scorer.score(candidate, targets)


def test_convenience_function_uses_default_policy() -> None:
    targets = NutrientTargets(calories=500)
    candidate = _candidate(calories=550)
    assert score_alignment(candidate, targets) == AlignmentScorer().score(candidate, targets)


def test_invalid_tolerance_and_threshold_are_rejected() -> None:
    with pytest.raises(ValueError):
        AlignmentScorer(tolerance=0)
    with pytest.raises(ValueError):
        AlignmentScorer(threshold=1.5)
    with pytest.raises(ValueError):
        AlignmentScorer(threshold=-0.1)
