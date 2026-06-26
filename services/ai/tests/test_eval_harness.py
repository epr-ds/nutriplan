"""Unit tests for the offline eval harness (AIA-701).

The harness grades a fixed set of cases through the production
:class:`~app.recommendations.alignment.RecommendationAligner` and aggregates the two headline
metrics. These tests pin exact, hand-computable numbers on a tiny set so the aggregation (and the
constraint-respect vs alignment distinction) is unambiguous, and prove the clock and scorer are
injected. No LLM, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.eval.case import EvalCase
from app.eval.harness import EvalHarness
from app.recommendations.alignment import RecommendationAligner
from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.scoring.scorer import AlignmentScorer

_FIXED = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)


def _recipe(
    name: str,
    *,
    calories: int,
    protein: int | None = None,
    ingredients: tuple[str, ...] = (),
) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("step",),
        nutrition=RecommendedNutrition(calories=calories, protein=protein),
        source=RecipeSource.SYNTHESIZED,
    )


def _cmd(**kwargs: object) -> RecommendationCommand:
    return RecommendationCommand(context=RecommendationContext.MEAL_PLAN, **kwargs)  # type: ignore[arg-type]


def _case(
    name: str, command: RecommendationCommand, recipes: tuple[RecommendedRecipe, ...]
) -> EvalCase:
    return EvalCase(name=name, prompt=name, command=command, recipes=recipes)


# On target (1.0), double calories (0.0, still respected), allergen leak (0.0, not respected),
# and a two-recipe case (1.0 + 0.5). Recipes: 5, violations: 1.
_SET: tuple[EvalCase, ...] = (
    _case("on-target", _cmd(calorie_target=400), (_recipe("On Target", calories=400),)),
    _case("double", _cmd(calorie_target=400), (_recipe("Double", calories=800),)),
    _case(
        "leak",
        _cmd(allergies=("peanuts",), calorie_target=400),
        (_recipe("Nutty", calories=400, ingredients=("peanuts",)),),
    ),
    _case(
        "twin",
        _cmd(calorie_target=400),
        (_recipe("Twin A", calories=400), _recipe("Twin B", calories=600)),
    ),
)


def test_run_aggregates_constraint_respect_and_mean_alignment() -> None:
    report = EvalHarness(clock=lambda: _FIXED).run(_SET)

    assert report.generated_at == "2026-06-25T12:00:00+00:00"
    assert report.total_cases == 4
    assert report.total_recipes == 5
    assert report.respected_recipes == 4
    assert report.constraint_respect == 0.8
    assert report.constraint_respect_pct == 80.0
    assert report.respected_cases == 3
    assert report.mean_alignment == 0.5
    assert report.mean_alignment_pct == 50.0


def test_per_case_results_carry_respect_and_score() -> None:
    report = EvalHarness().run(_SET)
    by_name = {case.name: case for case in report.cases}

    assert by_name["on-target"].respected is True
    assert by_name["on-target"].score == 1.0
    assert by_name["leak"].respected is False
    assert by_name["leak"].score == 0.0
    assert by_name["double"].respected is True  # poorly aligned but no hard violation


def test_a_case_without_constraints_is_a_harness_error() -> None:
    bad = _case("empty", _cmd(), (_recipe("Anything", calories=400),))

    with pytest.raises(ValueError, match="no constraints"):
        EvalHarness().run([bad])


def test_uses_the_injected_aligner_and_scorer() -> None:
    off = _case("off", _cmd(calorie_target=400), (_recipe("Off", calories=600),))  # scores 0.5

    strict = EvalHarness().run([off])
    lenient = EvalHarness(RecommendationAligner(AlignmentScorer(threshold=0.4))).run([off])

    assert strict.cases[0].alignment.aligned_count == 0
    assert lenient.cases[0].alignment.aligned_count == 1
