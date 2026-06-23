"""API tests for ``POST /ai/recommendations`` — the transport edge (AIA-201).

This slice owns bearer auth, request validation, and the ``AIRecommendationResponse`` envelope.
The recommendation service (wired in AIA-203) is overridden with a network-free instance that
returns no recipes, so these tests stay focused on transport and run offline; the real
recipe-mapping behaviour is covered by ``test_recommendations_endpoint.py``.
"""

from __future__ import annotations

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
from app.recommendations.service import RecommendationService
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-token"}
_PROBLEM_JSON = "application/problem+json"


def _empty_service() -> RecommendationService:
    provider = FakeLLMProvider([LLMResponse(content='{"recipes": []}', model="fake")])
    completion = StructuredCompletion(
        LLMClient(provider, RetryPolicy(max_retries=0)),
        StructuredOutputParser(RecommendationDraft),
        max_attempts=1,
    )
    return RecommendationService(
        build_recommendation_prompt_assembler(),
        completion,
        RecipeMapper(InMemoryRecipeCatalogue()),
    )


@pytest.fixture(autouse=True)
def _override_service():
    app.dependency_overrides[get_recommendation_service] = _empty_service
    yield
    app.dependency_overrides.pop(get_recommendation_service, None)


def _minimal_body() -> dict[str, object]:
    return {"context": "meal_plan", "language": "es"}


def test_requires_bearer_token() -> None:
    response = client.post("/ai/recommendations", json=_minimal_body())

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["status"] == 401


def test_rejects_unknown_context() -> None:
    response = client.post("/ai/recommendations", json={"context": "nope"}, headers=_AUTH)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)


def test_context_is_required() -> None:
    response = client.post("/ai/recommendations", json={"language": "es"}, headers=_AUTH)

    assert response.status_code == 422


def test_rejects_unsupported_language() -> None:
    response = client.post(
        "/ai/recommendations",
        json={"context": "meal_plan", "language": "fr"},
        headers=_AUTH,
    )

    assert response.status_code == 422


def test_rejects_unknown_meal_type() -> None:
    response = client.post(
        "/ai/recommendations",
        json={"context": "single_meal", "mealType": "brunch"},
        headers=_AUTH,
    )

    assert response.status_code == 422


def test_language_defaults_to_spanish() -> None:
    response = client.post("/ai/recommendations", json={"context": "single_meal"}, headers=_AUTH)

    assert response.status_code == 200


def test_returns_recommendation_response_shape() -> None:
    response = client.post("/ai/recommendations", json=_minimal_body(), headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] == []
    assert "reasoning" in body
    assert "nutritionalAlignment" in body


def test_accepts_full_camelcase_payload() -> None:
    body = {
        "context": "ingredient_based",
        "dietaryPreferences": {
            "dietType": "vegan",
            "allergies": ["peanuts"],
            "dailyCalorieTarget": 2000,
            "macroTargets": {
                "proteinGrams": 120,
                "carbsGrams": 200,
                "fatGrams": 60,
                "sugarGrams": 30,
            },
            "excludedIngredients": ["cilantro"],
            "cuisinePreferences": ["mexican"],
        },
        "availableIngredients": ["rice", "beans"],
        "mealType": "lunch",
        "calorieTarget": 700,
        "previousMeals": ["tacos"],
        "constraints": ["under 30 minutes"],
        "language": "en",
    }

    response = client.post("/ai/recommendations", json=body, headers=_AUTH)

    assert response.status_code == 200


def test_rejects_out_of_range_calorie_target() -> None:
    response = client.post(
        "/ai/recommendations",
        json={
            "context": "meal_plan",
            "dietaryPreferences": {"dailyCalorieTarget": 100},
        },
        headers=_AUTH,
    )

    assert response.status_code == 422
