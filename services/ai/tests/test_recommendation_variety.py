"""Unit tests for variety handling (AIA-205).

The diversifier is a deterministic, post-mapping pass that keeps recommendations fresh: it drops
recipes that repeat one of the user's ``previousMeals`` and skips candidates too similar (by
ingredient overlap) to ones already chosen. How aggressive it is comes from a configurable
:class:`VarietyStrength`. Everything here is pure, so the whole story is exercised offline.
"""

from __future__ import annotations

from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.variety import (
    RecommendationDiversifier,
    VarietyPolicy,
    VarietyStrength,
    build_diversifier,
)


def _recipe(name: str, ingredients: tuple[str, ...] = ()) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.strip().lower().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("Mix.",),
        nutrition=RecommendedNutrition(calories=300),
        source=RecipeSource.SYNTHESIZED,
    )


def _diversifier(strength: str) -> RecommendationDiversifier:
    return RecommendationDiversifier(VarietyPolicy.from_strength(strength))


# --- VarietyStrength.parse -----------------------------------------------------------------------


def test_parse_accepts_known_values_case_insensitively() -> None:
    assert VarietyStrength.parse("HIGH") is VarietyStrength.HIGH
    assert VarietyStrength.parse("  medium ") is VarietyStrength.MEDIUM
    assert VarietyStrength.parse(VarietyStrength.LOW) is VarietyStrength.LOW


def test_parse_falls_back_to_default_on_unknown_or_blank() -> None:
    assert VarietyStrength.parse("bogus") is VarietyStrength.default()
    assert VarietyStrength.parse(None) is VarietyStrength.default()
    assert VarietyStrength.parse("", default=VarietyStrength.OFF) is VarietyStrength.OFF


def test_default_strength_is_medium() -> None:
    assert VarietyStrength.default() is VarietyStrength.MEDIUM


# --- VarietyPolicy -------------------------------------------------------------------------------


def test_off_policy_is_disabled() -> None:
    assert VarietyPolicy.from_strength("off").enabled is False


def test_stronger_settings_use_lower_similarity_thresholds() -> None:
    low = VarietyPolicy.from_strength("low")
    medium = VarietyPolicy.from_strength("medium")
    high = VarietyPolicy.from_strength("high")

    assert low.enabled and medium.enabled and high.enabled
    # Lower threshold == easier to flag as a repeat/near-duplicate == stricter variety.
    assert high.previous_name_overlap < medium.previous_name_overlap <= low.previous_name_overlap
    assert (
        high.result_ingredient_overlap
        < medium.result_ingredient_overlap
        < low.result_ingredient_overlap
    )


# --- Diversifier: OFF passthrough ----------------------------------------------------------------


def test_off_is_a_passthrough_even_for_repeats() -> None:
    recipes = [_recipe("Avena con Frutas", ("avena",)), _recipe("Avena con Frutas", ("avena",))]

    out = _diversifier("off").diversify(recipes, previous_meals=["Avena con Frutas"])

    assert out == recipes


def test_off_still_respects_the_limit() -> None:
    recipes = [_recipe("A", ("x",)), _recipe("B", ("y",)), _recipe("C", ("z",))]

    out = _diversifier("off").diversify(recipes, limit=2)

    assert [r.name for r in out] == ["A", "B"]


# --- Diversifier: drop previous-meal repeats (AC1) -----------------------------------------------


def test_drops_a_recipe_repeating_a_previous_meal_case_insensitively() -> None:
    recipes = [
        _recipe("Avena con Frutas", ("avena",)),
        _recipe("Tostada de Aguacate", ("pan", "aguacate")),
    ]

    out = _diversifier("medium").diversify(recipes, previous_meals=["  avena CON frutas  "])

    assert [r.name for r in out] == ["Tostada de Aguacate"]


def test_no_previous_meals_drops_nothing() -> None:
    recipes = [
        _recipe("Avena con Frutas", ("avena",)),
        _recipe("Tostada de Aguacate", ("pan", "aguacate")),
    ]

    out = _diversifier("medium").diversify(recipes)

    assert [r.name for r in out] == ["Avena con Frutas", "Tostada de Aguacate"]


# --- Diversifier: ingredient diversity across the result (AC2) -----------------------------------


def test_drops_a_near_duplicate_by_ingredient_overlap() -> None:
    first = _recipe("Bowl A", ("oats", "milk", "banana"))
    near_duplicate = _recipe("Bowl B", ("oats", "milk", "banana", "honey"))  # 3/4 overlap

    out = _diversifier("medium").diversify([first, near_duplicate])

    assert [r.name for r in out] == ["Bowl A"]


def test_keeps_recipes_with_distinct_ingredients() -> None:
    first = _recipe("Bowl A", ("oats", "milk", "banana"))
    distinct = _recipe("Tacos", ("tortilla", "beans", "salsa"))

    out = _diversifier("medium").diversify([first, distinct])

    assert [r.name for r in out] == ["Bowl A", "Tacos"]


# --- Diversifier: configurable strength changes behavior (AC3) -----------------------------------


def test_high_drops_an_ingredient_overlap_that_medium_keeps() -> None:
    first = _recipe("Bowl A", ("oats", "milk", "banana"))
    half_overlap = _recipe("Bowl B", ("oats", "milk", "berries"))  # 2/4 = 0.5 overlap

    assert [r.name for r in _diversifier("high").diversify([first, half_overlap])] == ["Bowl A"]
    assert [r.name for r in _diversifier("medium").diversify([first, half_overlap])] == [
        "Bowl A",
        "Bowl B",
    ]


def test_strength_controls_fuzzy_previous_meal_matching() -> None:
    recipes = [_recipe("Grilled Chicken Tacos", ("chicken", "tortilla"))]

    # Shares two significant name tokens with the previous meal ("chicken", "tacos").
    high = _diversifier("high").diversify(recipes, previous_meals=["Chicken Tacos"])
    low = _diversifier("low").diversify(recipes, previous_meals=["Chicken Tacos"])

    assert high == []  # stronger variety treats the near-match as a repeat
    assert [r.name for r in low] == ["Grilled Chicken Tacos"]  # low only drops exact-name repeats


# --- Diversifier: limit --------------------------------------------------------------------------


def test_respects_the_limit_after_filtering() -> None:
    recipes = [_recipe("One", ("a",)), _recipe("Two", ("b",)), _recipe("Three", ("c",))]

    out = _diversifier("medium").diversify(recipes, limit=2)

    assert [r.name for r in out] == ["One", "Two"]


# --- build_diversifier ---------------------------------------------------------------------------


def test_build_diversifier_resolves_the_strength() -> None:
    assert build_diversifier("off").policy.enabled is False
    assert build_diversifier("high").policy.strength is VarietyStrength.HIGH
    assert build_diversifier("bogus").policy.strength is VarietyStrength.default()
