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
from app.recommendations.service import RecommendationService
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
    ]
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
) -> RecommendationService:
    client = LLMClient(provider, RetryPolicy(max_retries=0))
    completion = StructuredCompletion(
        client,
        StructuredOutputParser(RecommendationDraft),
        max_attempts=max_attempts,
        fallback=fallback,
    )
    mapper = RecipeMapper(catalogue or InMemoryRecipeCatalogue())
    return RecommendationService(build_recommendation_prompt_assembler(), completion, mapper)


def test_recommend_synthesizes_recipes_from_the_draft() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    [recipe] = service.recommend(_COMMAND)

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

    [recipe] = service.recommend(_COMMAND)

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

    assert service.recommend(_COMMAND) == []


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

    [recipe] = service.recommend(_COMMAND)

    assert recipe.name == "Avena con Frutas"
