"""Tests for hallucination detection + curated-recipe fallback (AIA-503).

"I get a safe result even when the model misbehaves." When the model returns nothing usable -- an
empty draft, or recipes that the validity / safety / bounds guards strip away -- the recommender
must not hand the user an empty answer if it can. :class:`CuratedRecipeFallback` detects that
situation and substitutes curated catalogue recipes (the production source is the P2 recipe search;
tests use an in-memory one), screening them through the same safety/bounds checks so a fallback can
never reintroduce an allergen. Every request and every fallback is recorded through a
:class:`FallbackTelemetry` port so the fallback *rate* is a first-class metric. No LLM, no I/O.
"""

from __future__ import annotations

import logging

from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.fallback import (
    CuratedRecipeFallback,
    FallbackEvent,
    FallbackReason,
    InMemoryCuratedRecipeSource,
    InMemoryFallbackTelemetry,
    LoggingFallbackTelemetry,
)
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


def _recipe(
    name: str,
    *,
    recipe_id: str | None = None,
    ingredients: tuple[str, ...] = ("something",),
    instructions: tuple[str, ...] = ("Do it.",),
    dietary_types: tuple[str, ...] = (),
    calories: int = 400,
) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=recipe_id or name.lower().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=instructions,
        nutrition=RecommendedNutrition(calories=calories),
        source=RecipeSource.CATALOGUE,
        dietary_types=dietary_types,
    )


def _command(*, count: int = 3, diet_type: str | None = None) -> RecommendationCommand:
    return RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        diet_type=diet_type,
        count=count,
    )


def _identity(recipes: tuple[RecommendedRecipe, ...]) -> tuple[RecommendedRecipe, ...]:
    return recipes


def _fallback(
    *,
    source: InMemoryCuratedRecipeSource | None = None,
    telemetry: InMemoryFallbackTelemetry | None = None,
) -> CuratedRecipeFallback:
    return CuratedRecipeFallback(
        source=source or InMemoryCuratedRecipeSource(),
        telemetry=telemetry or InMemoryFallbackTelemetry(),
    )


# --- happy path: the model's own recipes are kept -------------------------------------------------


def test_keeps_model_recipes_when_well_formed() -> None:
    telemetry = InMemoryFallbackTelemetry()
    model = (_recipe("Model Bowl"),)

    result = _fallback(telemetry=telemetry).resolve(
        model, _command(), mapped_count=1, screen=_identity
    )

    assert result == model
    assert telemetry.requests == 1
    assert telemetry.fallback_count == 0
    assert telemetry.rate == 0.0


def test_records_the_request_even_without_a_fallback() -> None:
    telemetry = InMemoryFallbackTelemetry()

    _fallback(telemetry=telemetry).resolve(
        (_recipe("Model Bowl"),), _command(), mapped_count=1, screen=_identity
    )

    assert telemetry.requests == 1


def test_drops_a_malformed_model_recipe_but_keeps_the_good_one() -> None:
    # A recipe with no ingredients is a hallucinated stub: dropped, but its well-formed sibling
    # survives, so no fallback is needed.
    telemetry = InMemoryFallbackTelemetry()
    good = _recipe("Real Dish")
    stub = _recipe("Empty Dish", ingredients=())
    source = InMemoryCuratedRecipeSource((_recipe("Curated"),))

    result = _fallback(source=source, telemetry=telemetry).resolve(
        (good, stub), _command(), mapped_count=2, screen=_identity
    )

    assert result == (good,)
    assert telemetry.fallback_count == 0


# --- fallback: the model produced nothing usable --------------------------------------------------


def test_falls_back_to_curated_when_the_model_returns_nothing() -> None:
    telemetry = InMemoryFallbackTelemetry()
    curated = (_recipe("Curated A"), _recipe("Curated B"))
    source = InMemoryCuratedRecipeSource(curated)

    result = _fallback(source=source, telemetry=telemetry).resolve(
        (), _command(), mapped_count=0, screen=_identity
    )

    assert result == curated
    assert telemetry.fallback_count == 1
    assert telemetry.rate == 1.0
    assert telemetry.events[0].reason is FallbackReason.EMPTY_OUTPUT


def test_marks_unusable_output_when_the_model_produced_recipes_that_were_all_stripped() -> None:
    # The model *did* return recipes (mapped_count > 0) but they were all removed upstream by the
    # safety / bounds guards, so the screened set arriving here is empty -> unusable output.
    telemetry = InMemoryFallbackTelemetry()
    source = InMemoryCuratedRecipeSource((_recipe("Curated"),))

    _fallback(source=source, telemetry=telemetry).resolve(
        (), _command(), mapped_count=3, screen=_identity
    )

    assert telemetry.events[0].reason is FallbackReason.UNUSABLE_OUTPUT
    assert telemetry.events[0].model_count == 3
    assert telemetry.events[0].curated_count == 1


def test_falls_back_when_every_model_recipe_is_malformed() -> None:
    telemetry = InMemoryFallbackTelemetry()
    source = InMemoryCuratedRecipeSource((_recipe("Curated"),))
    stub = _recipe("Stub", instructions=())

    result = _fallback(source=source, telemetry=telemetry).resolve(
        (stub,), _command(), mapped_count=1, screen=_identity
    )

    assert [recipe.name for recipe in result] == ["Curated"]
    assert telemetry.events[0].reason is FallbackReason.UNUSABLE_OUTPUT


def test_curated_recipes_are_screened_before_being_served() -> None:
    # The injected screen models the safety/bounds guards: a curated recipe it rejects must not be
    # served, even on a fallback.
    telemetry = InMemoryFallbackTelemetry()
    keep = _recipe("Safe Curated")
    drop = _recipe("Peanut Curated")
    source = InMemoryCuratedRecipeSource((drop, keep))

    def screen(recipes: tuple[RecommendedRecipe, ...]) -> tuple[RecommendedRecipe, ...]:
        return tuple(recipe for recipe in recipes if recipe.name != "Peanut Curated")

    result = _fallback(source=source, telemetry=telemetry).resolve(
        (), _command(), mapped_count=0, screen=screen
    )

    assert [recipe.name for recipe in result] == ["Safe Curated"]
    assert telemetry.events[0].curated_count == 1


def test_drops_a_malformed_curated_recipe() -> None:
    source = InMemoryCuratedRecipeSource((_recipe("Stub Curated", ingredients=()),))

    result = _fallback(source=source).resolve((), _command(), mapped_count=0, screen=_identity)

    assert result == ()


def test_caps_curated_fallback_at_the_requested_count() -> None:
    curated = tuple(_recipe(f"Curated {index}") for index in range(5))
    source = InMemoryCuratedRecipeSource(curated)

    result = _fallback(source=source).resolve(
        (), _command(count=2), mapped_count=0, screen=_identity
    )

    assert len(result) == 2


def test_returns_empty_when_the_model_fails_and_no_curated_recipes_exist() -> None:
    telemetry = InMemoryFallbackTelemetry()

    result = _fallback(telemetry=telemetry).resolve(
        (), _command(), mapped_count=0, screen=_identity
    )

    assert result == ()
    # A fallback was still attempted and recorded, even though nothing was available.
    assert telemetry.fallback_count == 1
    assert telemetry.events[0].curated_count == 0


def test_default_fallback_needs_no_arguments() -> None:
    result = CuratedRecipeFallback().resolve((), _command(), mapped_count=0, screen=_identity)

    assert result == ()


# --- in-memory curated source ---------------------------------------------------------------------


def test_source_filters_by_diet_type() -> None:
    vegan = _recipe("Vegan Bowl", dietary_types=("vegan",))
    omnivore = _recipe("Chicken Bowl", dietary_types=("omnivore",))
    source = InMemoryCuratedRecipeSource((vegan, omnivore))

    found = source.search(_command(diet_type="vegan"), limit=10)

    assert [recipe.name for recipe in found] == ["Vegan Bowl"]


def test_source_returns_all_when_no_diet_type_is_requested() -> None:
    source = InMemoryCuratedRecipeSource((_recipe("A"), _recipe("B")))

    assert len(source.search(_command(), limit=10)) == 2


def test_source_keeps_recipes_that_declare_no_dietary_types() -> None:
    # A recipe with no declared dietary types is diet-agnostic and should not be filtered out.
    source = InMemoryCuratedRecipeSource((_recipe("Plain"),))

    assert len(source.search(_command(diet_type="vegan"), limit=10)) == 1


def test_source_honours_the_limit() -> None:
    source = InMemoryCuratedRecipeSource(tuple(_recipe(f"R{i}") for i in range(5)))

    assert len(source.search(_command(), limit=2)) == 2


# --- telemetry ------------------------------------------------------------------------------------


def test_in_memory_rate_is_fallbacks_over_requests() -> None:
    telemetry = InMemoryFallbackTelemetry()
    telemetry.record_request()
    telemetry.record_request()
    telemetry.record_fallback(
        FallbackEvent(reason=FallbackReason.EMPTY_OUTPUT, model_count=0, curated_count=1)
    )

    assert telemetry.rate == 0.5


def test_in_memory_rate_is_zero_without_requests() -> None:
    assert InMemoryFallbackTelemetry().rate == 0.0


def test_logging_telemetry_warns_on_fallback(caplog) -> None:
    telemetry = LoggingFallbackTelemetry()

    with caplog.at_level(logging.WARNING, logger="app.recommendations.fallback"):
        telemetry.record_request()
        telemetry.record_fallback(
            FallbackEvent(reason=FallbackReason.EMPTY_OUTPUT, model_count=0, curated_count=2)
        )

    assert any(record.levelno == logging.WARNING for record in caplog.records)
