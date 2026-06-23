"""Unit tests for the recommendation alignment service (AIA-204).

The aligner is the bridge between recommended recipes and the deterministic AIA-106 scorer: it maps
a :class:`RecommendationCommand` onto nutrient targets and hard preferences, scores every recipe,
and aggregates the result into one response-level :class:`RecommendationAlignment` (score +
human-readable details). It does no I/O, so every case here is exact and offline.
"""

from __future__ import annotations

import pytest

from app.recommendations.alignment import (
    RecipeAlignment,
    RecommendationAligner,
)
from app.recommendations.commands import (
    MacroTargets,
    RecommendationCommand,
    RecommendationContext,
)
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.scoring.scorer import AlignmentScorer


def _recipe(
    name: str,
    *,
    calories: int,
    protein: int | None = None,
    carbs: int | None = None,
    fat: int | None = None,
    sugar: int | None = None,
    diets: tuple[str, ...] = (),
    ingredients: tuple[str, ...] = (),
) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("step",),
        nutrition=RecommendedNutrition(
            calories=calories, protein=protein, carbs=carbs, fat=fat, sugar=sugar
        ),
        source=RecipeSource.SYNTHESIZED,
        dietary_types=diets,
    )


def _command(
    *,
    diet_type: str | None = None,
    allergies: tuple[str, ...] = (),
    excluded_ingredients: tuple[str, ...] = (),
    calorie_target: int | None = None,
    macro_targets: MacroTargets | None = None,
) -> RecommendationCommand:
    return RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        diet_type=diet_type,
        allergies=allergies,
        excluded_ingredients=excluded_ingredients,
        calorie_target=calorie_target,
        macro_targets=macro_targets,
    )


def test_scores_a_recipe_that_hits_its_calorie_and_macro_targets() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("On Target", calories=400, protein=30)
    command = _command(calorie_target=400, macro_targets=MacroTargets(protein_grams=30))

    alignment = aligner.align([recipe], command)

    assert alignment is not None
    assert alignment.score == 1.0
    assert alignment.percentage == 100.0
    assert alignment.aligned_count == 1
    assert alignment.total == 1
    assert isinstance(alignment.recipes[0], RecipeAlignment)
    assert alignment.recipes[0].recipe_name == "On Target"


def test_returns_none_when_there_are_no_recipes() -> None:
    aligner = RecommendationAligner()

    assert aligner.align([], _command(calorie_target=400)) is None


def test_returns_none_when_there_is_nothing_to_align_against() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("Anything", calories=500)

    # No calorie/macro targets and no hard preferences -> no alignment to report.
    assert aligner.align([recipe], _command()) is None


def test_averages_the_score_across_recipes() -> None:
    aligner = RecommendationAligner()
    on_target = _recipe("On Target", calories=400, protein=30)
    too_high = _recipe("Too High", calories=800, protein=30)
    command = _command(calorie_target=400, macro_targets=MacroTargets(protein_grams=30))

    alignment = aligner.align([on_target, too_high], command)

    assert alignment is not None
    # On Target scores 1.0; Too High doubles its calories (closeness 0) -> 0.5. Mean = 0.75.
    assert alignment.score == 0.75
    assert alignment.percentage == 75.0
    assert alignment.aligned_count == 1
    assert alignment.total == 2
    assert "1 of 2" in alignment.details


def test_a_diet_violation_zeroes_that_recipe() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("Steak", calories=600, diets=("omnivore",))
    command = _command(diet_type="vegan")

    alignment = aligner.align([recipe], command)

    assert alignment is not None
    scored = alignment.recipes[0].alignment
    assert scored.score == 0.0
    assert not scored.aligned
    assert any("vegan" in violation for violation in scored.violations)
    assert alignment.aligned_count == 0


def test_an_excluded_ingredient_zeroes_that_recipe() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("Satay", calories=500, ingredients=("Peanuts", "chicken"))
    command = _command(allergies=("peanuts",))

    alignment = aligner.align([recipe], command)

    assert alignment is not None
    scored = alignment.recipes[0].alignment
    assert scored.score == 0.0
    assert any("peanuts" in violation for violation in scored.violations)


def test_uses_the_injected_scorer() -> None:
    # A permissive threshold flips an otherwise-unaligned recipe to aligned, proving the
    # injected scorer (not a hard-coded default) drives the result.
    aligner = RecommendationAligner(AlignmentScorer(threshold=0.4))
    too_high = _recipe("Too High", calories=800, protein=30)
    command = _command(calorie_target=400, macro_targets=MacroTargets(protein_grams=30))

    alignment = aligner.align([too_high], command)

    assert alignment is not None
    assert alignment.score == 0.5
    assert alignment.aligned_count == 1
    assert alignment.recipes[0].score == 0.5


def test_details_summarize_counts_and_percentage() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("On Target", calories=400)
    command = _command(calorie_target=400)

    alignment = aligner.align([recipe], command)

    assert alignment is not None
    assert "1 of 1" in alignment.details
    assert "100" in alignment.details


def test_unknown_actual_nutrition_cannot_be_confirmed_aligned() -> None:
    aligner = RecommendationAligner()
    recipe = _recipe("Mystery", calories=400)  # protein unknown
    command = _command(macro_targets=MacroTargets(protein_grams=40))

    alignment = aligner.align([recipe], command)

    assert alignment is not None
    assert alignment.score == pytest.approx(0.0)
    assert alignment.aligned_count == 0
