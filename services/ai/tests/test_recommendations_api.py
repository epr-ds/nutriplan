"""API tests for ``POST /ai/recommendations`` (AIA-201).

This slice owns the transport edge only: bearer auth, request validation, and the
``AIRecommendationResponse`` envelope. Prompt assembly, the LLM call, recipe mapping,
and nutritional alignment land in AIA-202..204, so the body is a validated stub here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-token"}
_PROBLEM_JSON = "application/problem+json"


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
