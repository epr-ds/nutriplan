"""Score how well recommended recipes align with the user's targets (AIA-204).

The recommendation use case produces recipes; this module says how well they fit. It maps the
caller's :class:`~app.recommendations.commands.RecommendationCommand` onto the AIA-106 vocabulary
(calorie/macro :class:`~app.scoring.types.NutrientTargets` plus hard
:class:`~app.scoring.types.Preferences`), scores every recipe with the deterministic
:class:`~app.scoring.scorer.AlignmentScorer`, and aggregates the per-recipe results into one
response-level :class:`RecommendationAlignment` (an overall score plus human-readable details) that
the API projects onto ``nutritionalAlignment``. It is pure -- no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.recommendations.commands import RecommendationCommand
from app.recommendations.recipes import RecommendedRecipe
from app.scoring.scorer import AlignmentScorer
from app.scoring.types import (
    NUTRIENTS,
    NutrientProfile,
    NutrientTargets,
    NutritionalAlignment,
    Preferences,
    ScoringCandidate,
)


@dataclass(frozen=True, slots=True)
class RecipeAlignment:
    """One recipe's alignment, kept alongside its identity for transparent details."""

    recipe_id: str
    recipe_name: str
    alignment: NutritionalAlignment

    @property
    def score(self) -> float:
        """The recipe's overall alignment score (0-1)."""
        return self.alignment.score


@dataclass(frozen=True, slots=True)
class RecommendationAlignment:
    """How well a set of recommendations fits the user's targets and preferences.

    ``score`` is the mean overall score across the scored recipes (0-1); ``percentage`` exposes it
    as 0-100 for the wire. ``aligned_count``/``total`` and ``details`` summarize the per-recipe
    breakdown kept in ``recipes``.
    """

    score: float
    aligned_count: int
    total: int
    details: str
    recipes: tuple[RecipeAlignment, ...]

    @property
    def percentage(self) -> float:
        """The overall score as a 0-100 percentage."""
        return round(self.score * 100, 2)


class RecommendationAligner:
    """Score recommended recipes against a command's targets and preferences (AIA-106)."""

    def __init__(self, scorer: AlignmentScorer | None = None) -> None:
        self._scorer = scorer or AlignmentScorer()

    def align(
        self,
        recipes: Sequence[RecommendedRecipe],
        command: RecommendationCommand,
    ) -> RecommendationAlignment | None:
        """Return the overall alignment, or ``None`` when there is nothing to score against."""
        if not recipes:
            return None
        targets = _targets(command)
        preferences = _preferences(command)
        if not _has_criteria(targets, preferences):
            return None

        scored = tuple(
            RecipeAlignment(
                recipe_id=recipe.id,
                recipe_name=recipe.name,
                alignment=self._scorer.score(_candidate(recipe), targets, preferences),
            )
            for recipe in recipes
        )
        mean = sum(item.score for item in scored) / len(scored)
        aligned_count = sum(1 for item in scored if item.alignment.aligned)
        return RecommendationAlignment(
            score=round(mean, 4),
            aligned_count=aligned_count,
            total=len(scored),
            details=_details(scored, aligned_count),
            recipes=scored,
        )


def _targets(command: RecommendationCommand) -> NutrientTargets:
    macros = command.macro_targets
    return NutrientTargets(
        calories=command.effective_calories(),
        protein=macros.protein_grams if macros else None,
        carbs=macros.carbs_grams if macros else None,
        fat=macros.fat_grams if macros else None,
        sugar=macros.sugar_grams if macros else None,
    )


def _preferences(command: RecommendationCommand) -> Preferences:
    required = frozenset({command.diet_type}) if command.diet_type else frozenset()
    excluded = frozenset(command.allergies) | frozenset(command.excluded_ingredients)
    return Preferences(required_diets=required, excluded_ingredients=excluded)


def _candidate(recipe: RecommendedRecipe) -> ScoringCandidate:
    nutrition = recipe.nutrition
    return ScoringCandidate(
        nutrition=NutrientProfile(
            calories=nutrition.calories,
            protein=nutrition.protein,
            carbs=nutrition.carbs,
            fat=nutrition.fat,
            sugar=nutrition.sugar,
        ),
        diets=frozenset(recipe.dietary_types),
        ingredients=frozenset(item.name for item in recipe.ingredients),
    )


def _has_criteria(targets: NutrientTargets, preferences: Preferences) -> bool:
    targeted = any(getattr(targets, nutrient) is not None for nutrient in NUTRIENTS)
    constrained = bool(preferences.required_diets or preferences.excluded_ingredients)
    return targeted or constrained


def _details(recipes: tuple[RecipeAlignment, ...], aligned_count: int) -> str:
    total = len(recipes)
    average = round(sum(item.score for item in recipes) / total * 100, 1)
    summary = (
        f"{aligned_count} of {total} recommendations align with your nutritional "
        f"targets and preferences (average {average}%)."
    )
    conflicted = sum(1 for item in recipes if item.alignment.violations)
    if conflicted:
        summary += f" {conflicted} of {total} conflict with your dietary preferences."
    return summary
