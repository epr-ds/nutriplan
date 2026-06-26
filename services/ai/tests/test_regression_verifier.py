"""Tests for the regression verifier's mechanics -- proving the gate actually trips (AIA-704).

A release gate that can never fail is worthless, so these tests inject a deliberately broken filter
and confirm the verifier reports the regression: an unsafe recipe surviving, a forbidden ingredient
leaking, and -- in the other direction -- a safe recipe wrongly dropped. They also pin the report's
``ok`` flag, the case-name-prefixed failure formatting, and the ``expected_unsafe_ids`` derivation.
The corpus-against-real-filter guarantee lives in ``test_safety_regression.py``.
"""

from __future__ import annotations

from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.safety import AllergenFilter
from app.regression.case import SafetyCase
from app.regression.verifier import SafetyRegressionVerifier


def _recipe(name: str, *ingredients: str) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("Mix.",),
        nutrition=RecommendedNutrition(calories=300),
        source=RecipeSource.SYNTHESIZED,
    )


class _PassthroughFilter(AllergenFilter):
    """A broken filter that enforces nothing -- stands in for a total safety regression."""

    def filter(self, recipes, *, allergies=(), excluded=()):  # type: ignore[override]
        return tuple(recipes)


_SHELLFISH_CASE = SafetyCase(
    name="shellfish",
    allergies=("shellfish",),
    excluded=(),
    recipes=(
        _recipe("Veggie Bowl", "broccoli", "rice"),
        _recipe("Shrimp Paella", "rice", "grilled shrimp"),
    ),
    expected_safe_ids=("veggie-bowl",),
    forbidden_substrings=("shrimp",),
)


def test_real_filter_passes_a_well_formed_case() -> None:
    report = SafetyRegressionVerifier().verify((_SHELLFISH_CASE,))

    assert report.ok is True
    assert report.failures == ()
    assert report.outcomes[0].kept_ids == ("veggie-bowl",)


def test_broken_filter_is_caught_as_a_regression() -> None:
    report = SafetyRegressionVerifier(_PassthroughFilter()).verify((_SHELLFISH_CASE,))

    assert report.ok is False
    joined = " ".join(report.failures)
    assert "shrimp-paella" in joined  # the unsafe recipe survived
    assert "shrimp" in joined  # the forbidden ingredient leaked
    assert all(failure.startswith("shellfish:") for failure in report.failures)


def test_over_removal_is_caught_as_a_regression() -> None:
    # A case with nothing to remove: the real filter keeps both, but a passthrough that somehow
    # drops one would fail. Here we assert the inverse via a filter that removes everything.
    class _DropEverything(AllergenFilter):
        def filter(self, recipes, *, allergies=(), excluded=()):  # type: ignore[override]
            return ()

    case = SafetyCase(
        name="safe-only",
        allergies=("tree nuts",),
        excluded=(),
        recipes=(_recipe("Tree Tomato Salad", "tree tomato", "lettuce"),),
        expected_safe_ids=("tree-tomato-salad",),
        forbidden_substrings=("walnut",),
    )

    report = SafetyRegressionVerifier(_DropEverything()).verify((case,))

    assert report.ok is False
    assert any("was dropped" in failure for failure in report.failures)


def test_expected_unsafe_ids_are_everything_not_expected_safe() -> None:
    assert _SHELLFISH_CASE.expected_unsafe_ids == ("shrimp-paella",)


def test_outcome_ok_is_false_only_when_there_are_failures() -> None:
    report = SafetyRegressionVerifier().verify((_SHELLFISH_CASE,))

    assert report.outcomes[0].ok is True
    assert report.outcomes[0].failures == ()
