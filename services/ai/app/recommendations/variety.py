"""Keep recommendations varied: drop previous-meal repeats and near-duplicates (AIA-205).

Even with the AIA-202 prompt nudging the model to avoid the user's ``previousMeals``, nothing
*guarantees* variety -- a model may still echo a recent dinner or return three look-alike recipes.
This module adds a deterministic, post-mapping pass that enforces it. A
:class:`RecommendationDiversifier` drops recipes whose name repeats a previous meal and skips
candidates too similar (by ingredient overlap) to ones already chosen, so what the user sees stays
fresh across requests. How aggressive it is comes from a :class:`VarietyStrength` knob
(``AI_VARIETY_STRENGTH``), making the behaviour configurable without touching the API contract.

The "diversity across cuisines" the story asks for is approximated by ingredient-set similarity:
``RecommendedRecipe`` carries no cuisine field, and dishes from the same cuisine share much of their
ingredient profile, so a low ingredient overlap is a good proxy for culinary variety. Everything
here is pure -- no LLM, no I/O -- so it is fully unit-testable and reproducible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.recommendations.catalogue import normalize_name
from app.recommendations.recipes import RecommendedRecipe

# A tiny, language-spanning stopword set so name similarity keys on the dish, not its glue words
# ("Avena con Frutas" vs "Avena con Nueces" should not look alike just because both say "con").
_NAME_STOPWORDS = frozenset(
    {
        "a",
        "al",
        "an",
        "and",
        "con",
        "de",
        "del",
        "el",
        "en",
        "la",
        "las",
        "los",
        "of",
        "on",
        "the",
        "with",
        "y",
    }
)


class VarietyStrength(StrEnum):
    """How aggressively to enforce variety (``AI_VARIETY_STRENGTH``)."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def default(cls) -> VarietyStrength:
        """The strength used when none is configured."""
        return cls.MEDIUM

    @classmethod
    def parse(
        cls,
        value: VarietyStrength | str | None,
        *,
        default: VarietyStrength | None = None,
    ) -> VarietyStrength:
        """Map a configured value onto a member, case-insensitively.

        Accepts already-typed members and strings. Unknown/blank values fall back to ``default``
        (or :meth:`default` when none is given) so a typo in configuration degrades to a sensible
        policy rather than crashing the service.
        """
        fallback = default if default is not None else cls.default()
        if isinstance(value, cls):
            return value
        if value is None:
            return fallback
        token = str(value).strip().lower()
        for member in cls:
            if member.value == token:
                return member
        return fallback


@dataclass(frozen=True, slots=True)
class VarietyPolicy:
    """The thresholds a :class:`VarietyStrength` resolves to.

    ``enabled`` toggles the whole pass (``OFF`` is a passthrough). ``previous_name_overlap`` is the
    minimum name-token Jaccard at which a recipe counts as a repeat of a ``previousMeals`` entry
    (``1.0`` = only an exact normalized-name match). ``result_ingredient_overlap`` is the ingredient
    Jaccard at or above which a candidate is "too similar" to one already selected and is skipped.
    Lower thresholds mean stricter variety.
    """

    strength: VarietyStrength
    enabled: bool
    previous_name_overlap: float
    result_ingredient_overlap: float

    @classmethod
    def from_strength(cls, strength: VarietyStrength | str | None) -> VarietyPolicy:
        """Resolve a strength (member, string, or ``None``) into its policy."""
        return _POLICIES[VarietyStrength.parse(strength)]


_POLICIES: dict[VarietyStrength, VarietyPolicy] = {
    VarietyStrength.OFF: VarietyPolicy(
        VarietyStrength.OFF, enabled=False, previous_name_overlap=1.0, result_ingredient_overlap=1.0
    ),
    VarietyStrength.LOW: VarietyPolicy(
        VarietyStrength.LOW, enabled=True, previous_name_overlap=1.0, result_ingredient_overlap=0.9
    ),
    VarietyStrength.MEDIUM: VarietyPolicy(
        VarietyStrength.MEDIUM,
        enabled=True,
        previous_name_overlap=0.6,
        result_ingredient_overlap=0.7,
    ),
    VarietyStrength.HIGH: VarietyPolicy(
        VarietyStrength.HIGH, enabled=True, previous_name_overlap=0.3, result_ingredient_overlap=0.5
    ),
}


class RecommendationDiversifier:
    """Filter a recipe list down to a varied subset for one request (AIA-205)."""

    def __init__(self, policy: VarietyPolicy | None = None) -> None:
        self._policy = policy or VarietyPolicy.from_strength(VarietyStrength.default())

    @property
    def policy(self) -> VarietyPolicy:
        """The thresholds this diversifier enforces."""
        return self._policy

    def diversify(
        self,
        recipes: Sequence[RecommendedRecipe],
        *,
        previous_meals: Sequence[str] = (),
        limit: int | None = None,
    ) -> list[RecommendedRecipe]:
        """Drop previous-meal repeats and near-duplicate recipes, then cap the result at ``limit``.

        With variety ``OFF`` this is a passthrough (optionally trimmed to ``limit``). Otherwise it
        keeps source order -- the model's ranking -- and greedily admits a recipe only when it does
        not repeat a previous meal and is not too similar (by ingredient overlap) to an
        already-admitted one.
        """
        if not self._policy.enabled:
            return _capped(recipes, limit)

        previous = [tokens for name in previous_meals if (tokens := _name_tokens(name))]
        selected: list[RecommendedRecipe] = []
        chosen_ingredients: list[frozenset[str]] = []
        for recipe in recipes:
            if self._repeats_previous(recipe, previous):
                continue
            ingredients = _ingredient_tokens(recipe)
            if any(
                _jaccard(ingredients, taken) >= self._policy.result_ingredient_overlap
                for taken in chosen_ingredients
            ):
                continue
            selected.append(recipe)
            chosen_ingredients.append(ingredients)
            if limit is not None and len(selected) >= limit:
                break
        return selected

    def _repeats_previous(self, recipe: RecommendedRecipe, previous: list[frozenset[str]]) -> bool:
        if not previous:
            return False
        tokens = _name_tokens(recipe.name)
        if not tokens:
            return False
        threshold = self._policy.previous_name_overlap
        return any(_jaccard(tokens, prev) >= threshold for prev in previous)


def build_diversifier(strength: VarietyStrength | str | None) -> RecommendationDiversifier:
    """Build a diversifier for a configured strength (used by the service factory)."""
    return RecommendationDiversifier(VarietyPolicy.from_strength(strength))


def _capped(recipes: Sequence[RecommendedRecipe], limit: int | None) -> list[RecommendedRecipe]:
    items = list(recipes)
    return items if limit is None else items[:limit]


def _name_tokens(name: str) -> frozenset[str]:
    """Significant, normalized name tokens, ignoring glue words.

    Falls back to the raw tokens when a name is *only* stopwords so it can still match itself.
    """
    words = normalize_name(name).split()
    significant = {word for word in words if word not in _NAME_STOPWORDS}
    return frozenset(significant or words)


def _ingredient_tokens(recipe: RecommendedRecipe) -> frozenset[str]:
    return frozenset(normalize_name(item.name) for item in recipe.ingredients if item.name.strip())


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Set-similarity in ``[0, 1]``: empties are identical; a single empty shares nothing."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
