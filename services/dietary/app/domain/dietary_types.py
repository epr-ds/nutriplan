"""Shared dietary-type vocabulary for the Dietary Planning bounded context.

``DietaryType`` is a value enum used by **both** aggregates: a meal plan declares the diet it
targets and a recipe declares the diets it is compatible with. It lives in its own module (a small
"shared kernel") so neither aggregate has to import the other just to reference the shared
vocabulary.
"""

from __future__ import annotations

from enum import StrEnum


class DietaryType(StrEnum):
    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    KETO = "keto"
    PALEO = "paleo"
