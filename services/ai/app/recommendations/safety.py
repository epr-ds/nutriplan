"""Allergy / exclusion enforcement: the deterministic post-filter behind the prompt (AIA-501).

The recommendation prompt already frames the user's allergies and excluded ingredients as hard
"never include" constraints (AIA-202), but a language model can still slip one through. This module
is the safety net that makes the guarantee real: :class:`AllergenFilter` removes any recommended
recipe whose ingredients hit one of the caller's allergies or excluded ingredients, and records
every removal through a :class:`GuardrailTelemetry` port so violations are **logged and counted**.

Matching is lexical and deliberately conservative -- for an allergy, over-removing is the safe
failure mode, so a recipe is dropped whenever its ingredients contain the forbidden term (matched on
word stems, case-insensitively, tolerant of singular/plural). On top of that, the standard allergen
families are expanded to their common member ingredients (``shellfish`` -> shrimp/crab/lobster...,
``tree_nuts`` -> almond/walnut..., ``milk`` -> cheese/butter/cream...) so an allergen catches the
foods that contain it, not just its own name. Everything here is pure -- no LLM, no I/O -- so it is
fully unit-testable and reproducible, and it sets up the AIA-506 adversarial guardrail suite.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.recommendations.recipes import RecommendedRecipe

_LOGGER = logging.getLogger("app.recommendations.safety")

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


class ViolationKind(StrEnum):
    """Why a recipe was removed: it hit an allergy or an excluded ingredient."""

    ALLERGY = "allergy"
    EXCLUSION = "exclusion"


@dataclass(frozen=True, slots=True)
class GuardrailViolation:
    """A single removed (recipe, forbidden-term) pair, the unit the telemetry counts."""

    recipe_id: str
    recipe_name: str
    term: str
    kind: ViolationKind


@runtime_checkable
class GuardrailTelemetry(Protocol):
    """A write port: record that the post-filter removed a recipe for a forbidden term."""

    def record(self, violation: GuardrailViolation) -> None: ...


class InMemoryGuardrailTelemetry:
    """Collects violations in a list so tests can assert what was removed and counted."""

    def __init__(self) -> None:
        self.violations: list[GuardrailViolation] = []

    def record(self, violation: GuardrailViolation) -> None:
        self.violations.append(violation)

    @property
    def count(self) -> int:
        """Total number of recorded violations."""
        return len(self.violations)

    def count_for(self, kind: ViolationKind) -> int:
        """How many recorded violations were of ``kind``."""
        return sum(1 for violation in self.violations if violation.kind is kind)

    @property
    def terms(self) -> list[str]:
        """The forbidden term of each recorded violation, in record order."""
        return [violation.term for violation in self.violations]


class LoggingGuardrailTelemetry:
    """Emits one WARNING per violation -- a guardrail trip is operationally noteworthy."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record(self, violation: GuardrailViolation) -> None:
        self._logger.warning(
            "guardrail violation: kind=%s term=%s recipe=%s",
            violation.kind.value,
            violation.term,
            violation.recipe_id,
        )


# --- Allergen vocabulary -------------------------------------------------------------------------
# Canonical allergen families and the everyday ingredients that carry them. The map lets an allergy
# like "shellfish" catch "shrimp" even though the words do not overlap. It is intentionally curated
# and conservative (common members only); user-entered free-text exclusions get no expansion -- they
# are matched literally.

_ALLERGEN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "milk": ("milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "whey", "casein", "ghee"),
    "eggs": ("egg", "mayonnaise", "meringue", "albumin"),
    "peanuts": ("peanut", "groundnut"),
    "tree_nuts": (
        "almond",
        "walnut",
        "pecan",
        "cashew",
        "pistachio",
        "hazelnut",
        "macadamia",
        "brazil nut",
        "praline",
        "marzipan",
    ),
    "soy": ("soy", "soya", "soybean", "edamame", "tofu", "tempeh", "miso"),
    "wheat": ("wheat", "bread", "pasta", "couscous", "bulgur", "semolina", "farro", "cracker"),
    "gluten": ("gluten", "wheat", "barley", "rye", "malt", "bread", "pasta"),
    "fish": (
        "fish",
        "salmon",
        "tuna",
        "cod",
        "halibut",
        "sardine",
        "anchovy",
        "trout",
        "mackerel",
        "tilapia",
        "haddock",
    ),
    "shellfish": (
        "shellfish",
        "shrimp",
        "prawn",
        "crab",
        "lobster",
        "crayfish",
        "clam",
        "mussel",
        "oyster",
        "scallop",
        "squid",
        "calamari",
    ),
    "sesame": ("sesame", "tahini"),
}

# How users phrase an allergy -> the canonical family above.
_ALLERGEN_SYNONYMS: dict[str, str] = {
    "milk": "milk",
    "dairy": "milk",
    "lactose": "milk",
    "egg": "eggs",
    "eggs": "eggs",
    "peanut": "peanuts",
    "peanuts": "peanuts",
    "groundnut": "peanuts",
    "groundnuts": "peanuts",
    "nut": "tree_nuts",
    "nuts": "tree_nuts",
    "tree nut": "tree_nuts",
    "tree nuts": "tree_nuts",
    "treenuts": "tree_nuts",
    "soy": "soy",
    "soya": "soy",
    "soybean": "soy",
    "soybeans": "soy",
    "wheat": "wheat",
    "gluten": "gluten",
    "fish": "fish",
    "shellfish": "shellfish",
    "crustacean": "shellfish",
    "crustaceans": "shellfish",
    "sesame": "sesame",
}


def _stem(word: str) -> str:
    """Fold a word to a crude stem so singular/plural forms match (``eggs`` ~ ``egg``)."""
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _stems(text: str) -> frozenset[str]:
    """All stemmed word tokens in ``text`` (lower-cased, punctuation-split)."""
    return frozenset(_stem(word) for word in _WORD_SPLIT.split(text.casefold()) if word)


def _phrase_stems(text: str) -> tuple[str, ...]:
    """The stemmed words of a forbidden phrase, in order (every one must be present to match)."""
    return tuple(_stem(word) for word in _WORD_SPLIT.split(text.casefold()) if word)


def _normalize_term(term: str) -> str:
    """Normalize a user allergy phrase for synonym lookup (``Tree_Nuts`` -> ``tree nuts``)."""
    return " ".join(_WORD_SPLIT.split(term.casefold()))


def _triggers(term: str, kind: ViolationKind) -> tuple[tuple[str, ...], ...]:
    """The stemmed phrases that, if fully present in a recipe, mean ``term`` is violated.

    Always includes the term itself; for an allergy that names a known family, also includes each of
    that family's member ingredients so the allergen catches the foods that contain it.
    """
    phrases = [_phrase_stems(term)]
    if kind is ViolationKind.ALLERGY:
        canonical = _ALLERGEN_SYNONYMS.get(_normalize_term(term))
        if canonical is not None:
            phrases.extend(_phrase_stems(member) for member in _ALLERGEN_EXPANSIONS[canonical])
    return tuple(phrase for phrase in phrases if phrase)


def _violates(recipe_stems: frozenset[str], term: str, kind: ViolationKind) -> bool:
    """Whether ``term`` is present: any trigger phrase fully contained in the recipe stems."""
    return any(all(word in recipe_stems for word in phrase) for phrase in _triggers(term, kind))


class AllergenFilter:
    """Drop recommended recipes that violate the caller's allergies or excluded ingredients."""

    def __init__(self, telemetry: GuardrailTelemetry | None = None) -> None:
        self._telemetry = telemetry or LoggingGuardrailTelemetry()

    def filter(
        self,
        recipes: tuple[RecommendedRecipe, ...],
        *,
        allergies: tuple[str, ...] = (),
        excluded: tuple[str, ...] = (),
    ) -> tuple[RecommendedRecipe, ...]:
        """Return only the safe recipes, recording one violation per (recipe, matched term)."""
        if not allergies and not excluded:
            return tuple(recipes)
        kept: list[RecommendedRecipe] = []
        for recipe in recipes:
            violations = self._violations_for(recipe, allergies, excluded)
            if violations:
                for violation in violations:
                    self._telemetry.record(violation)
            else:
                kept.append(recipe)
        return tuple(kept)

    def _violations_for(
        self,
        recipe: RecommendedRecipe,
        allergies: tuple[str, ...],
        excluded: tuple[str, ...],
    ) -> list[GuardrailViolation]:
        stems: set[str] = set()
        for ingredient in recipe.ingredients:
            stems.update(_stems(ingredient.name))
        recipe_stems = frozenset(stems)
        found: list[GuardrailViolation] = []
        for term in allergies:
            if _violates(recipe_stems, term, ViolationKind.ALLERGY):
                found.append(self._violation(recipe, term, ViolationKind.ALLERGY))
        for term in excluded:
            if _violates(recipe_stems, term, ViolationKind.EXCLUSION):
                found.append(self._violation(recipe, term, ViolationKind.EXCLUSION))
        return found

    @staticmethod
    def _violation(recipe: RecommendedRecipe, term: str, kind: ViolationKind) -> GuardrailViolation:
        return GuardrailViolation(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            term=term,
            kind=kind,
        )
