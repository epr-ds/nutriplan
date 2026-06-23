"""Tests for context + dietary-preferences-aware prompt assembly (AIA-202).

The assembler turns a :class:`RecommendationCommand` into a localized, versioned prompt:
a distinct template per ``context`` with the caller's dietary profile, available
ingredients, and meal type injected. It produces the prompt only -- the LLM call and
recipe mapping are AIA-203 -- so every test here asserts on the rendered messages.
"""

from __future__ import annotations

from app.prompts.library import (
    RECOMMEND_INGREDIENT_BASED_ID,
    RECOMMEND_MEAL_PLAN_ID,
    RECOMMEND_SINGLE_MEAL_ID,
    build_default_catalog,
)
from app.prompts.telemetry import InMemoryPromptTelemetry
from app.prompts.types import Locale
from app.recommendations import (
    MacroTargets,
    MealType,
    RecommendationCommand,
    RecommendationContext,
    RecommendationPromptAssembler,
    build_recommendation_prompt_assembler,
)


def _assembler(telemetry: InMemoryPromptTelemetry | None = None) -> RecommendationPromptAssembler:
    return build_recommendation_prompt_assembler(telemetry=telemetry)


def _full_command(context: RecommendationContext) -> RecommendationCommand:
    return RecommendationCommand(
        context=context,
        diet_type="vegan",
        allergies=("peanuts",),
        excluded_ingredients=("cilantro",),
        cuisine_preferences=("mexican",),
        daily_calorie_target=2000,
        macro_targets=MacroTargets(protein_grams=120, carbs_grams=200, fat_grams=60),
        available_ingredients=("rice", "beans"),
        meal_type=MealType.LUNCH,
        previous_meals=("tacos",),
        constraints=("under 30 minutes",),
    )


def _user_text(rendered) -> str:
    return rendered.messages[-1].content


def test_each_context_uses_a_distinct_prompt() -> None:
    assembler = _assembler()

    refs = {
        ctx: assembler.assemble(RecommendationCommand(context=ctx)).ref.id
        for ctx in RecommendationContext
    }

    assert refs == {
        RecommendationContext.MEAL_PLAN: RECOMMEND_MEAL_PLAN_ID,
        RecommendationContext.SINGLE_MEAL: RECOMMEND_SINGLE_MEAL_ID,
        RecommendationContext.INGREDIENT_BASED: RECOMMEND_INGREDIENT_BASED_ID,
    }
    assert len(set(refs.values())) == 3


def test_meal_plan_injects_full_dietary_profile() -> None:
    rendered = _assembler().assemble(_full_command(RecommendationContext.MEAL_PLAN))

    text = _user_text(rendered)
    assert "vegan" in text
    assert "peanuts" in text
    assert "cilantro" in text
    assert "mexican" in text
    assert "2000" in text
    assert "120" in text  # protein macro target
    assert "tacos" in text  # previousMeals
    assert "under 30 minutes" in text  # constraints
    assert "$" not in text  # every placeholder substituted


def test_single_meal_honours_meal_type() -> None:
    rendered = _assembler().assemble(_full_command(RecommendationContext.SINGLE_MEAL))

    assert "lunch" in _user_text(rendered)


def test_ingredient_based_lists_available_ingredients() -> None:
    rendered = _assembler().assemble(_full_command(RecommendationContext.INGREDIENT_BASED))

    text = _user_text(rendered)
    assert "rice" in text
    assert "beans" in text


def test_empty_profile_uses_neutral_fillers() -> None:
    rendered = _assembler().assemble(RecommendationCommand(context=RecommendationContext.MEAL_PLAN))

    text = _user_text(rendered)
    assert "$" not in text  # no unsubstituted placeholders despite an empty profile
    assert "none" in text.lower()


def test_spanish_localization_translates_persona_and_fillers() -> None:
    rendered = _assembler().assemble(
        RecommendationCommand(context=RecommendationContext.MEAL_PLAN), locale="es"
    )

    assert rendered.ref.locale is Locale.ES
    system_text = rendered.messages[0].content
    assert "español" in system_text.lower() or "dietista" in system_text.lower()
    assert "ninguna" in _user_text(rendered).lower()  # localized "none" filler


def test_spanish_injects_values() -> None:
    rendered = _assembler().assemble(
        _full_command(RecommendationContext.INGREDIENT_BASED), locale=Locale.ES
    )

    text = _user_text(rendered)
    assert "rice" in text and "beans" in text
    assert "vegan" in text


def test_assembler_records_prompt_version() -> None:
    telemetry = InMemoryPromptTelemetry()

    _assembler(telemetry).assemble(RecommendationCommand(context=RecommendationContext.MEAL_PLAN))

    assert telemetry.records
    assert telemetry.records[-1].version


def test_every_context_prompt_ships_in_en_and_es() -> None:
    catalog = build_default_catalog()

    for prompt_id in (
        RECOMMEND_MEAL_PLAN_ID,
        RECOMMEND_SINGLE_MEAL_ID,
        RECOMMEND_INGREDIENT_BASED_ID,
    ):
        assert prompt_id in catalog.ids
        assert catalog.available_locales(prompt_id) == frozenset({Locale.EN, Locale.ES})
        en = catalog.get(prompt_id, Locale.EN)
        es = catalog.get(prompt_id, Locale.ES)
        assert en.version == es.version


def test_macro_targets_are_formatted() -> None:
    rendered = _assembler().assemble(
        RecommendationCommand(
            context=RecommendationContext.SINGLE_MEAL,
            macro_targets=MacroTargets(protein_grams=140, carbs_grams=80, fat_grams=40),
        )
    )

    text = _user_text(rendered)
    assert "140" in text
    assert "80" in text
    assert "40" in text
