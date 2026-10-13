"""The recipe-catalogue port and an in-memory adapter (AIA-203, AC1).

To make a recommendation *real* rather than invented, the mapper first asks a catalogue whether a
proposed recipe already exists. :class:`RecipeCatalogue` is the port that hides where the catalogue
lives -- the production adapter will query the Dietary service's recipe repository (P2), while tests
and offline development use :class:`InMemoryRecipeCatalogue`. Matching is by a normalized name so
trivial casing/whitespace differences still resolve to the same entry.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from app.recommendations.recipes import RecommendedRecipe

_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Reduce a recipe name to a case- and whitespace-insensitive key."""
    return _WHITESPACE.sub(" ", name.strip().casefold())


@runtime_checkable
class RecipeCatalogue(Protocol):
    """A lookup of known, curated recipes the recommender can link to."""

    def find(self, name: str) -> RecommendedRecipe | None:
        """Return the catalogue recipe matching ``name``, or ``None`` if there is none."""
        ...


class InMemoryRecipeCatalogue:
    """A network-free :class:`RecipeCatalogue` backed by a name index."""

    def __init__(self, recipes: Iterable[RecommendedRecipe] = ()) -> None:
        self._by_name: dict[str, RecommendedRecipe] = {
            normalize_name(recipe.name): recipe for recipe in recipes
        }

    def find(self, name: str) -> RecommendedRecipe | None:
        return self._by_name.get(normalize_name(name))
