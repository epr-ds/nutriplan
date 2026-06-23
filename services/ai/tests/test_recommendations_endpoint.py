"""HTTP tests for ``POST /ai/recommendations`` once it returns real recipes (AIA-203).

AIA-201 shipped this route as a validated stub; AIA-203 wires the recommendation service behind it,
so the response now carries real, usable recipes. The service is overridden with a network-free,
fake-backed instance, so the endpoint is exercised end to end (request -> command -> prompt -> draft
-> mapped recipes -> camelCase envelope) without calling a provider.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_recommendation_service
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse
from app.main import app
from app.recommendations.assembler import build_recommendation_prompt_assembler
from app.recommendations.catalogue import InMemoryRecipeCatalogue
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

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-token"}

_DRAFT = {
    "recipes": [
        {
            "name": "Avena con Frutas",
            "description": "Desayuno rapido.",
            "ingredients": [{"name": "avena", "quantity": 80, "unit": "g"}],
            "instructions": ["Mezcla.", "Sirve."],
            "prep_time_minutes": 5,
            "cook_time_minutes": 0,
            "servings": 1,
            "nutrition": {"calories": 350, "protein": 12, "carbs": 60, "fat": 7, "sugar": 15},
            "dietary_types": ["vegetarian"],
        },
        {
            "name": "Tostada de Aguacate",
            "description": "Almuerzo ligero.",
            "ingredients": [
                {"name": "pan integral", "quantity": 2, "unit": "rebanadas"},
                {"name": "aguacate", "quantity": 1, "unit": "unidad"},
            ],
            "instructions": ["Tuesta el pan.", "Agrega el aguacate."],
            "prep_time_minutes": 8,
            "cook_time_minutes": 3,
            "servings": 1,
            "nutrition": {"calories": 420, "protein": 11, "carbs": 38, "fat": 26, "sugar": 4},
            "dietary_types": ["vegetarian", "vegan"],
        },
    ],
    "reasoning": "Estas recetas se ajustan a tu objetivo de 400 kcal y tus preferencias veganas.",
}


def _fake_service() -> RecommendationService:
    provider = FakeLLMProvider([LLMResponse(content=json.dumps(_DRAFT), model="fake")])
    completion = StructuredCompletion(
        LLMClient(provider, RetryPolicy(max_retries=0)),
        StructuredOutputParser(RecommendationDraft),
        max_attempts=1,
    )
    linked = RecommendedRecipe(
        id="recipe-oatmeal",
        name="Avena con Frutas",
        servings=2,
        ingredients=(RecommendedIngredient(name="avena", quantity=70, unit="g"),),
        instructions=("Paso del catalogo.",),
        nutrition=RecommendedNutrition(calories=360, protein=13, carbs=58, fat=8),
        source=RecipeSource.CATALOGUE,
    )
    mapper = RecipeMapper(InMemoryRecipeCatalogue([linked]))
    return RecommendationService(build_recommendation_prompt_assembler(), completion, mapper)


@pytest.fixture(autouse=True)
def _override_service():
    app.dependency_overrides[get_recommendation_service] = _fake_service
    yield
    app.dependency_overrides.pop(get_recommendation_service, None)


def _body() -> dict[str, object]:
    return {"context": "meal_plan", "language": "es"}


def _recommendations() -> list[dict]:
    response = client.post("/ai/recommendations", json=_body(), headers=_AUTH)
    return response.json()["recommendations"]


def test_returns_real_recipes() -> None:
    response = client.post("/ai/recommendations", json=_body(), headers=_AUTH)

    assert response.status_code == 200
    recipes = response.json()["recommendations"]
    assert [r["name"] for r in recipes] == ["Avena con Frutas", "Tostada de Aguacate"]


def test_links_matched_recipe_to_the_catalogue_id() -> None:
    recipes = _recommendations()

    # First recipe matched the catalogue, so it carries the catalogue id, not a synthesized slug.
    assert recipes[0]["id"] == "recipe-oatmeal"
    assert recipes[1]["id"] == "tostada-de-aguacate"


def test_each_recipe_has_ingredients_steps_and_nutrition() -> None:
    recipes = _recommendations()

    for recipe in recipes:
        assert recipe["ingredients"], "expected at least one ingredient"
        assert recipe["instructions"], "expected at least one step"
        assert recipe["nutritionalInfo"]["calories"] is not None


def test_response_uses_camelcase_recipe_shape() -> None:
    synthesized = _recommendations()[1]

    assert synthesized["nutritionalInfo"]["protein"] == 11
    assert synthesized["dietaryTypes"] == ["vegetarian", "vegan"]
    assert synthesized["prepTime"] == 8
    assert synthesized["ingredients"][0]["name"] == "pan integral"


def _targeted_body() -> dict[str, object]:
    # A per-meal calorie target gives the AIA-106 scorer something to align against.
    return {"context": "single_meal", "language": "es", "calorieTarget": 400}


def test_reasoning_is_returned() -> None:
    body = client.post("/ai/recommendations", json=_body(), headers=_AUTH).json()

    assert body["reasoning"] == _DRAFT["reasoning"]


def test_alignment_is_null_without_targets_or_preferences() -> None:
    body = client.post("/ai/recommendations", json=_body(), headers=_AUTH).json()

    # No targets and no hard preferences -> nothing to align against.
    assert body["nutritionalAlignment"] is None


def test_alignment_is_scored_when_targets_are_present() -> None:
    body = client.post("/ai/recommendations", json=_targeted_body(), headers=_AUTH).json()

    alignment = body["nutritionalAlignment"]
    assert alignment is not None
    assert isinstance(alignment["score"], (int, float))
    assert 0.0 <= alignment["score"] <= 100.0
    assert "2 of 2" in alignment["details"]


def test_still_requires_a_bearer_token() -> None:
    response = client.post("/ai/recommendations", json=_body())

    assert response.status_code == 401
