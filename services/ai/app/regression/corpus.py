"""The golden allergy / exclusion regression corpus: the cases asserted every run (AIA-704).

Each :class:`~app.regression.case.SafetyCase` pins a realistic constraint scenario and the exact
recipes the production :class:`~app.recommendations.safety.AllergenFilter` must keep. The corpus is
deliberately broad: it exercises every allergen family the filter expands (peanuts, shellfish, tree
nuts, milk, eggs, soy, gluten/wheat, fish, sesame), a user-typed exclusion that gets no family
expansion, a multi-constraint request, the case-insensitive path, and an over-match guard that must
*not* drop a safe recipe sharing a single word with an allergen. Family-expansion cases (a
``shellfish`` allergy catching ``shrimp``) are what make this more than a restatement of the unit
tests: lose the expansion and a known-unsafe recipe survives, and the gate fails.

Recipe ids are derived from the name so the cases read clearly and the expected-safe sets stay
legible. ``forbidden_substrings`` name the ingredient fragments that must never survive, checked
independently of the filter.
"""

from __future__ import annotations

from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.regression.case import SafetyCase


def _recipe(name: str, *ingredients: str) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("Prepare and serve.",),
        nutrition=RecommendedNutrition(calories=400),
        source=RecipeSource.SYNTHESIZED,
    )


GOLDEN_SAFETY_CASES: tuple[SafetyCase, ...] = (
    SafetyCase(
        name="peanut-allergy-literal",
        allergies=("peanuts",),
        excluded=(),
        recipes=(
            _recipe("Oatmeal Bowl", "oats", "banana"),
            _recipe("PB Toast", "whole-grain bread", "peanut butter"),
        ),
        expected_safe_ids=("oatmeal-bowl",),
        forbidden_substrings=("peanut",),
    ),
    SafetyCase(
        name="shellfish-family-expansion",
        allergies=("shellfish",),
        excluded=(),
        recipes=(
            _recipe("Veggie Stir-Fry", "broccoli", "rice"),
            _recipe("Seafood Paella", "rice", "grilled shrimp", "saffron"),
        ),
        expected_safe_ids=("veggie-stir-fry",),
        forbidden_substrings=("shrimp",),
    ),
    SafetyCase(
        name="tree-nuts-family-expansion",
        allergies=("tree nuts",),
        excluded=(),
        recipes=(
            _recipe("Garden Salad", "spinach", "tomato"),
            _recipe("Walnut Salad", "spinach", "toasted walnuts"),
        ),
        expected_safe_ids=("garden-salad",),
        forbidden_substrings=("walnut",),
    ),
    SafetyCase(
        name="dairy-synonym-to-milk",
        allergies=("dairy",),
        excluded=(),
        recipes=(
            _recipe("Fruit Salad", "apple", "grapes"),
            _recipe("Mac and Cheese", "macaroni", "cheddar cheese"),
        ),
        expected_safe_ids=("fruit-salad",),
        forbidden_substrings=("cheese",),
    ),
    SafetyCase(
        name="eggs-allergy",
        allergies=("eggs",),
        excluded=(),
        recipes=(
            _recipe("Toast and Jam", "sourdough", "jam"),
            _recipe("Veggie Omelette", "eggs", "spinach"),
        ),
        expected_safe_ids=("toast-and-jam",),
        forbidden_substrings=("egg",),
    ),
    SafetyCase(
        name="soy-family-expansion",
        allergies=("soy",),
        excluded=(),
        recipes=(
            _recipe("Beef Bowl", "beef", "rice"),
            _recipe("Tofu Scramble", "tofu", "peppers"),
        ),
        expected_safe_ids=("beef-bowl",),
        forbidden_substrings=("tofu",),
    ),
    SafetyCase(
        name="gluten-family-expansion",
        allergies=("gluten",),
        excluded=(),
        recipes=(
            _recipe("Rice Bowl", "rice", "vegetables"),
            _recipe("Spaghetti Marinara", "pasta", "tomato sauce"),
        ),
        expected_safe_ids=("rice-bowl",),
        forbidden_substrings=("pasta",),
    ),
    SafetyCase(
        name="fish-family-expansion",
        allergies=("fish",),
        excluded=(),
        recipes=(
            _recipe("Chicken Plate", "chicken breast", "potato"),
            _recipe("Grilled Salmon", "salmon fillet", "lemon"),
        ),
        expected_safe_ids=("chicken-plate",),
        forbidden_substrings=("salmon",),
    ),
    SafetyCase(
        name="sesame-family-expansion",
        allergies=("sesame",),
        excluded=(),
        recipes=(
            _recipe("Carrot Sticks", "carrot", "ranch"),
            _recipe("Hummus Plate", "chickpeas", "tahini"),
        ),
        expected_safe_ids=("carrot-sticks",),
        forbidden_substrings=("tahini",),
    ),
    SafetyCase(
        name="exclusion-no-expansion",
        allergies=(),
        excluded=("cilantro",),
        recipes=(
            _recipe("Plain Rice", "rice", "salt"),
            _recipe("Fresh Salsa", "tomato", "fresh cilantro", "onion"),
        ),
        expected_safe_ids=("plain-rice",),
        forbidden_substrings=("cilantro",),
    ),
    SafetyCase(
        name="multi-constraint-bowl",
        allergies=("peanuts", "shellfish"),
        excluded=("cilantro",),
        recipes=(
            _recipe("Plain Salad", "lettuce", "cucumber"),
            _recipe("Thai Peanut Noodles", "peanut sauce", "noodles"),
            _recipe("Shrimp Curry", "shrimp", "coconut milk"),
            _recipe("Cilantro Lime Bowl", "rice", "fresh cilantro"),
        ),
        expected_safe_ids=("plain-salad",),
        forbidden_substrings=("peanut", "shrimp", "cilantro"),
    ),
    SafetyCase(
        name="tree-nuts-no-overmatch",
        allergies=("tree nuts",),
        excluded=(),
        recipes=(
            _recipe("Tree Tomato Salad", "tree tomato", "lettuce"),
            _recipe("Plain Oats", "oats", "water"),
        ),
        expected_safe_ids=("tree-tomato-salad", "plain-oats"),
        forbidden_substrings=("almond", "walnut", "pecan", "cashew"),
    ),
    SafetyCase(
        name="peanut-allergy-case-insensitive",
        allergies=("Peanuts",),
        excluded=(),
        recipes=(
            _recipe("Apple Slices", "apple"),
            _recipe("PB Cups", "PEANUT BUTTER"),
        ),
        expected_safe_ids=("apple-slices",),
        forbidden_substrings=("peanut",),
    ),
)
"""The fixed, version-controlled corpus the ``regression`` CI gate asserts on every run."""
