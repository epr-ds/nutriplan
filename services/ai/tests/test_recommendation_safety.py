"""Tests for the allergy / exclusion post-filter and its telemetry (AIA-501).

The prompt already tells the model to never include an allergen or excluded ingredient (AIA-202),
but a model can still slip. The :class:`AllergenFilter` is the deterministic safety net behind the
prompt: it drops any recommended recipe whose ingredients hit one of the caller's allergies or
excluded ingredients, and records every removal through a :class:`GuardrailTelemetry` port so the
violations are logged and counted. Everything here is pure -- no LLM, no I/O -- so it is fully
unit-testable and reproducible.
"""

from __future__ import annotations

import logging

from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.safety import (
    AllergenFilter,
    GuardrailViolation,
    InMemoryGuardrailTelemetry,
    LoggingGuardrailTelemetry,
    ViolationKind,
)


def _recipe(recipe_id: str, name: str, *ingredient_names: str) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=recipe_id,
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=n) for n in ingredient_names),
        instructions=("Mix.",),
        nutrition=RecommendedNutrition(calories=300),
        source=RecipeSource.SYNTHESIZED,
    )


def _filter(telemetry: InMemoryGuardrailTelemetry | None = None) -> AllergenFilter:
    return AllergenFilter(telemetry or InMemoryGuardrailTelemetry())


def test_keeps_every_recipe_when_there_is_nothing_to_enforce() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (
        _recipe("r1", "Oatmeal", "oats", "banana"),
        _recipe("r2", "Grilled Chicken", "chicken breast", "rice"),
    )

    kept = _filter(telemetry).filter(recipes, allergies=(), excluded=())

    assert kept == recipes
    assert telemetry.count == 0


def test_drops_recipe_whose_ingredient_literally_contains_the_allergen() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (
        _recipe("safe", "Oatmeal", "oats", "banana"),
        _recipe("nope", "PB Toast", "whole-grain bread", "peanut butter"),
    )

    kept = _filter(telemetry).filter(recipes, allergies=("peanuts",), excluded=())

    assert [r.id for r in kept] == ["safe"]
    assert telemetry.violations == [
        GuardrailViolation(
            recipe_id="nope",
            recipe_name="PB Toast",
            term="peanuts",
            kind=ViolationKind.ALLERGY,
        )
    ]


def test_expands_shellfish_to_its_member_ingredients() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (_recipe("paella", "Seafood Paella", "rice", "Grilled Shrimp", "saffron"),)

    kept = _filter(telemetry).filter(recipes, allergies=("shellfish",), excluded=())

    assert kept == ()
    assert telemetry.count == 1
    assert telemetry.violations[0].term == "shellfish"
    assert telemetry.violations[0].kind is ViolationKind.ALLERGY


def test_expands_tree_nuts_to_member_ingredients() -> None:
    recipes = (_recipe("salad", "Walnut Salad", "spinach", "toasted walnuts"),)

    kept = _filter().filter(recipes, allergies=("tree nuts",), excluded=())

    assert kept == ()


def test_dairy_synonym_maps_to_the_milk_expansion() -> None:
    recipes = (_recipe("mac", "Mac & Cheese", "macaroni", "cheddar cheese"),)

    kept = _filter().filter(recipes, allergies=("dairy",), excluded=())

    assert kept == ()


def test_excluded_ingredient_is_removed_and_tagged_as_an_exclusion() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (_recipe("salsa", "Pico de Gallo", "tomato", "Fresh Cilantro", "onion"),)

    kept = _filter(telemetry).filter(recipes, allergies=(), excluded=("cilantro",))

    assert kept == ()
    assert telemetry.violations[0].kind is ViolationKind.EXCLUSION
    assert telemetry.violations[0].term == "cilantro"


def test_multiword_allergen_does_not_overmatch_on_one_shared_word() -> None:
    # "tree nuts" must not strike a recipe that only shares the word "tree".
    recipes = (_recipe("ttomato", "Tree Tomato Salad", "tree tomato", "lettuce"),)

    kept = _filter().filter(recipes, allergies=("tree nuts",), excluded=())

    assert [r.id for r in kept] == ["ttomato"]


def test_matches_across_singular_and_plural_forms() -> None:
    plural_term = _recipe("omelette", "Omelette", "two eggs", "butter")
    singular_term = _recipe("scramble", "Scramble", "scrambled eggs")
    filt = _filter()

    assert filt.filter((plural_term,), allergies=("egg",), excluded=()) == ()
    assert filt.filter((singular_term,), allergies=("eggs",), excluded=()) == ()


def test_matching_is_case_insensitive() -> None:
    recipes = (_recipe("pb", "PB Cups", "PEANUT BUTTER"),)

    kept = _filter().filter(recipes, allergies=("Peanuts",), excluded=())

    assert kept == ()


def test_records_one_violation_per_matched_term_but_drops_once() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (_recipe("both", "Thai Bowl", "peanut sauce", "fresh cilantro"),)

    kept = _filter(telemetry).filter(recipes, allergies=("peanuts",), excluded=("cilantro",))

    assert kept == ()
    assert telemetry.count == 2
    assert telemetry.count_for(ViolationKind.ALLERGY) == 1
    assert telemetry.count_for(ViolationKind.EXCLUSION) == 1
    assert {v.term for v in telemetry.violations} == {"peanuts", "cilantro"}


def test_unrelated_recipe_is_never_touched() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    recipes = (_recipe("bowl", "Veggie Bowl", "broccoli", "brown rice", "chicken"),)

    kept = _filter(telemetry).filter(
        recipes, allergies=("peanuts", "shellfish"), excluded=("cilantro",)
    )

    assert kept == recipes
    assert telemetry.count == 0


def test_blank_terms_are_ignored() -> None:
    recipes = (_recipe("bowl", "Veggie Bowl", "broccoli", "rice"),)

    kept = _filter().filter(recipes, allergies=("", "   "), excluded=("",))

    assert kept == recipes


def test_filter_defaults_to_a_usable_telemetry_when_constructed_bare() -> None:
    recipes = (_recipe("pb", "PB Toast", "peanut butter"),)

    kept = AllergenFilter().filter(recipes, allergies=("peanuts",), excluded=())

    assert kept == ()


def test_logging_telemetry_warns_once_per_violation(caplog) -> None:
    telemetry = LoggingGuardrailTelemetry()
    violation = GuardrailViolation(
        recipe_id="nope",
        recipe_name="PB Toast",
        term="peanuts",
        kind=ViolationKind.ALLERGY,
    )

    with caplog.at_level(logging.WARNING, logger="app.recommendations.safety"):
        telemetry.record(violation)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    message = caplog.records[0].getMessage()
    assert "nope" in message
    assert "peanuts" in message
