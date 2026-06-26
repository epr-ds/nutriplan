"""End-to-end tests for the recommendation application service (AIA-203).

The service ties AIA-202's prompt assembler to the AIA-104 structured-completion loop and the
AIA-203 recipe mapper: it assembles a localized prompt, asks the model for a schema-constrained
draft, and maps that draft onto recipes (linking real ones, synthesizing the rest). The LLM is the
network-free :class:`FakeLLMProvider`, so the whole path is exercised offline.
"""

from __future__ import annotations

import json

from app.completions import CachedCompletionService
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse, Role
from app.recommendations.assembler import build_recommendation_prompt_assembler
from app.recommendations.bounds import (
    InMemoryBoundsTelemetry,
    NutritionBoundsGuard,
)
from app.recommendations.catalogue import InMemoryRecipeCatalogue
from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.draft import RecommendationDraft
from app.recommendations.mapper import RecipeMapper
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.safety import (
    AllergenFilter,
    InMemoryGuardrailTelemetry,
    ViolationKind,
)
from app.recommendations.service import RecommendationService
from app.recommendations.variety import RecommendationDiversifier, VarietyPolicy
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

_DRAFT = {
    "recipes": [
        {
            "name": "Avena con Frutas",
            "description": "Un desayuno rapido.",
            "ingredients": [{"name": "avena", "quantity": 80, "unit": "g"}],
            "instructions": ["Mezcla los ingredientes.", "Sirve frio."],
            "prep_time_minutes": 5,
            "cook_time_minutes": 0,
            "servings": 1,
            "nutrition": {"calories": 350, "protein": 12, "carbs": 60, "fat": 7, "sugar": 15},
            "dietary_types": ["vegetarian"],
        }
    ],
    "reasoning": "Elegi avena porque encaja con tu objetivo de 350 kcal y tus preferencias.",
}

_COMMAND = RecommendationCommand(
    context=RecommendationContext.MEAL_PLAN,
    diet_type="vegan",
    allergies=("peanuts",),
)


def _response(text: str) -> LLMResponse:
    return LLMResponse(content=text, model="fake")


def _service(
    provider: FakeLLMProvider,
    *,
    catalogue: InMemoryRecipeCatalogue | None = None,
    fallback=None,
    max_attempts: int = 1,
    diversifier: RecommendationDiversifier | None = None,
    safety_filter: AllergenFilter | None = None,
    bounds_guard: NutritionBoundsGuard | None = None,
) -> RecommendationService:
    client = LLMClient(provider, RetryPolicy(max_retries=0))
    completion = StructuredCompletion(
        client,
        StructuredOutputParser(RecommendationDraft),
        max_attempts=max_attempts,
        fallback=fallback,
    )
    mapper = RecipeMapper(catalogue or InMemoryRecipeCatalogue())
    return RecommendationService(
        build_recommendation_prompt_assembler(),
        completion,
        mapper,
        diversifier=diversifier,
        safety_filter=safety_filter,
        bounds_guard=bounds_guard,
    )


def test_recommend_synthesizes_recipes_from_the_draft() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    [recipe] = service.recommend(_COMMAND).recipes

    assert recipe.name == "Avena con Frutas"
    assert recipe.source is RecipeSource.SYNTHESIZED
    assert recipe.ingredients == (RecommendedIngredient(name="avena", quantity=80, unit="g"),)
    assert recipe.instructions == ("Mezcla los ingredientes.", "Sirve frio.")
    assert recipe.nutrition == RecommendedNutrition(
        calories=350, protein=12, carbs=60, fat=7, sugar=15
    )


def test_request_carries_assembled_prompt_and_schema_constraint() -> None:
    provider = FakeLLMProvider([_response(json.dumps(_DRAFT))])

    _service(provider).recommend(_COMMAND)

    call = provider.calls[0]
    # The assembled prompt (system persona) reached the provider...
    assert any(m.role is Role.SYSTEM and "registered-dietitian" in m.content for m in call.messages)
    # ...and the structured-output schema was attached as the response format.
    assert call.response_format is not None
    assert call.response_format.name == "RecommendationDraft"


def test_recommend_links_a_catalogue_recipe() -> None:
    linked = RecommendedRecipe(
        id="recipe-oatmeal",
        name="Avena con Frutas",
        servings=2,
        ingredients=(RecommendedIngredient(name="avena", quantity=70, unit="g"),),
        instructions=("Paso del catalogo.",),
        nutrition=RecommendedNutrition(calories=360, protein=13, carbs=58, fat=8),
        source=RecipeSource.CATALOGUE,
    )
    service = _service(
        FakeLLMProvider([_response(json.dumps(_DRAFT))]),
        catalogue=InMemoryRecipeCatalogue([linked]),
    )

    [recipe] = service.recommend(_COMMAND).recipes

    assert recipe is linked
    assert recipe.source is RecipeSource.CATALOGUE


def test_locale_selects_the_spanish_prompt() -> None:
    provider = FakeLLMProvider([_response(json.dumps(_DRAFT))])

    _service(provider).recommend(_COMMAND, locale="es")

    assert any(
        m.role is Role.SYSTEM and "dietista-nutricionista" in m.content
        for m in provider.calls[0].messages
    )


def test_falls_back_to_no_recommendations_on_bad_output() -> None:
    service = _service(
        FakeLLMProvider([_response("not json at all")]),
        fallback=lambda _error: RecommendationDraft(),
    )

    result = service.recommend(_COMMAND)

    assert result.recipes == ()
    assert result.reasoning is None
    assert result.alignment is None


def test_composes_over_a_cached_completer() -> None:
    # The structured loop must accept any LLMCompleter, not just the bare client, so the
    # production wiring can layer caching/budgets underneath it.
    cached = CachedCompletionService(FakeLLMProvider([_response(json.dumps(_DRAFT))]))
    completion = StructuredCompletion(cached, StructuredOutputParser(RecommendationDraft))
    service = RecommendationService(
        build_recommendation_prompt_assembler(),
        completion,
        RecipeMapper(InMemoryRecipeCatalogue()),
    )

    [recipe] = service.recommend(_COMMAND).recipes

    assert recipe.name == "Avena con Frutas"


def test_recommend_surfaces_model_reasoning() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    result = service.recommend(_COMMAND)

    assert result.reasoning == _DRAFT["reasoning"]


def test_recommend_scores_alignment_against_targets() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))
    command = RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        calorie_target=350,  # matches the draft recipe's 350 kcal exactly
    )

    result = service.recommend(command)

    assert result.alignment is not None
    assert result.alignment.total == 1
    assert result.alignment.recipes[0].recipe_name == "Avena con Frutas"
    assert result.alignment.percentage == 100.0


def test_recommend_skips_alignment_without_targets_or_preferences() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    result = service.recommend(RecommendationCommand(context=RecommendationContext.MEAL_PLAN))

    assert result.alignment is None


def test_recommend_drops_meals_listed_in_previous_meals() -> None:
    # Variety is on by default (medium): a recommendation repeating a previous meal is removed.
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))
    command = RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        previous_meals=("Avena con Frutas",),
    )

    result = service.recommend(command)

    assert result.recipes == ()
    assert result.alignment is None


def test_variety_off_keeps_previous_meal_repeats() -> None:
    # The strength is configurable: OFF turns the diversifier into a passthrough.
    service = _service(
        FakeLLMProvider([_response(json.dumps(_DRAFT))]),
        diversifier=RecommendationDiversifier(VarietyPolicy.from_strength("off")),
    )
    command = RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        previous_meals=("Avena con Frutas",),
    )

    result = service.recommend(command)

    assert [recipe.name for recipe in result.recipes] == ["Avena con Frutas"]


_ALLERGEN_DRAFT = {
    "recipes": [
        {
            "name": "Safe Oatmeal",
            "ingredients": [{"name": "oats"}, {"name": "banana"}],
            "instructions": ["Mix."],
            "servings": 1,
            "nutrition": {"calories": 300},
        },
        {
            "name": "Peanut Toast",
            "ingredients": [{"name": "bread"}, {"name": "peanut butter"}],
            "instructions": ["Spread."],
            "servings": 1,
            "nutrition": {"calories": 320},
        },
    ],
}


def test_recommend_post_filters_allergen_violations_and_counts_them() -> None:
    # AIA-501 AC2/AC3: even if the model returns a recipe with an allergen, the post-filter drops
    # it before the user sees it, and the violation is recorded through the telemetry port.
    telemetry = InMemoryGuardrailTelemetry()
    service = _service(
        FakeLLMProvider([_response(json.dumps(_ALLERGEN_DRAFT))]),
        safety_filter=AllergenFilter(telemetry),
    )
    command = RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        allergies=("peanuts",),
    )

    result = service.recommend(command)

    assert [recipe.name for recipe in result.recipes] == ["Safe Oatmeal"]
    assert telemetry.count == 1
    assert telemetry.violations[0].kind is ViolationKind.ALLERGY
    assert telemetry.violations[0].term == "peanuts"


def test_recommend_keeps_violating_recipe_when_no_allergies_declared() -> None:
    telemetry = InMemoryGuardrailTelemetry()
    service = _service(
        FakeLLMProvider([_response(json.dumps(_ALLERGEN_DRAFT))]),
        safety_filter=AllergenFilter(telemetry),
    )

    result = service.recommend(RecommendationCommand(context=RecommendationContext.MEAL_PLAN))

    assert {recipe.name for recipe in result.recipes} == {"Safe Oatmeal", "Peanut Toast"}
    assert telemetry.count == 0


_INSANE_DRAFT = {
    "recipes": [
        {
            "name": "Sane Soup",
            "ingredients": [{"name": "broth"}],
            "instructions": ["Heat."],
            "servings": 1,
            "nutrition": {"calories": 300},
        },
        {
            "name": "Mega Cake",
            "ingredients": [{"name": "flour"}],
            "instructions": ["Bake."],
            "servings": 1,
            "nutrition": {"calories": 9000},
        },
    ],
}


def test_recommend_rejects_out_of_bounds_recipe_and_counts_it() -> None:
    # AIA-502 AC1/AC3: the model returned a recipe far over the calorie ceiling; the bounds guard
    # rejects it (the good one survives) and the rejection is recorded.
    telemetry = InMemoryBoundsTelemetry()
    service = _service(
        FakeLLMProvider([_response(json.dumps(_INSANE_DRAFT))]),
        bounds_guard=NutritionBoundsGuard(telemetry),
    )

    result = service.recommend(RecommendationCommand(context=RecommendationContext.MEAL_PLAN))

    assert [recipe.name for recipe in result.recipes] == ["Sane Soup"]
    assert telemetry.rejection_count == 1


def test_recommend_clamps_calorie_target_before_prompting() -> None:
    # AIA-502 AC2: an out-of-bounds target is clamped to the sane range before the model is asked,
    # so the prompt (and the alignment) work from 1200 rather than 800.
    telemetry = InMemoryBoundsTelemetry()
    provider = FakeLLMProvider([_response(json.dumps(_DRAFT))])
    service = _service(provider, bounds_guard=NutritionBoundsGuard(telemetry))
    command = RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        daily_calorie_target=800,
    )

    service.recommend(command)

    assert telemetry.clamps[0].clamped == 1200
    rendered = " ".join(message.content for message in provider.calls[0].messages)
    assert "1200 kcal" in rendered
