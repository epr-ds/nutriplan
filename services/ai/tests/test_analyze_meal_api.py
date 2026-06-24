"""HTTP tests for ``POST /ai/analyze-meal`` — the transport edge (AIA-301).

This slice owns Bearer auth, request validation, and the ``NutritionalAnalysisResponse`` envelope.
The analysis service (real estimation lands in AIA-302) is overridden with a deterministic fake, so
these tests run offline and also pin the request -> command mapping and the response projection.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analysis.alignment import MealAligner, MealReference
from app.analysis.commands import MealAnalysisCommand
from app.analysis.result import AnalyzedNutrition, MealAnalysis
from app.api.analysis import _to_command
from app.api.deps import get_meal_analysis_service
from app.api.schemas import AnalyzeMealRequest
from app.main import app

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-token"}
_PROBLEM_JSON = "application/problem+json"


class _FakeAnalysisService:
    """Captures the command it was handed and returns a canned analysis."""

    def __init__(self, result: MealAnalysis) -> None:
        self.result = result
        self.commands: list[MealAnalysisCommand] = []

    def analyze(self, command: MealAnalysisCommand) -> MealAnalysis:
        self.commands.append(command)
        return self.result


_RESULT = MealAnalysis(
    nutrition=AnalyzedNutrition(calories=500, protein=20, carbs=60, fat=18, sugar=12),
    warnings=("Contains a common allergen: peanuts.",),
)
_service = _FakeAnalysisService(_RESULT)


@pytest.fixture(autouse=True)
def _override_service():
    _service.commands.clear()
    app.dependency_overrides[get_meal_analysis_service] = lambda: _service
    yield
    app.dependency_overrides.pop(get_meal_analysis_service, None)


def _body() -> dict[str, object]:
    return {"description": "Oatmeal with banana and peanut butter"}


def test_requires_bearer_token() -> None:
    response = client.post("/ai/analyze-meal", json=_body())

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["status"] == 401


def test_description_is_required() -> None:
    response = client.post("/ai/analyze-meal", json={}, headers=_AUTH)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)


def test_accepts_free_text_description_only() -> None:
    response = client.post("/ai/analyze-meal", json=_body(), headers=_AUTH)

    assert response.status_code == 200


def test_accepts_structured_ingredients() -> None:
    body = {
        "description": "Breakfast bowl",
        "ingredients": [
            {"name": "oats", "quantity": 80, "unit": "g"},
            {"name": "banana", "quantity": 1, "unit": "unit", "calories": 100},
        ],
    }

    response = client.post("/ai/analyze-meal", json=body, headers=_AUTH)

    assert response.status_code == 200
    # The structured ingredients reached the application command.
    assert [item.name for item in _service.commands[0].ingredients] == ["oats", "banana"]


def test_returns_nutritional_analysis_shape() -> None:
    body = client.post("/ai/analyze-meal", json=_body(), headers=_AUTH).json()

    assert body["nutritionalInfo"]["calories"] == 500
    assert body["nutritionalInfo"]["protein"] == 20
    assert body["warnings"] == ["Contains a common allergen: peanuts."]
    assert "alignment" in body


def test_projects_an_empty_analysis_as_nulls() -> None:
    app.dependency_overrides[get_meal_analysis_service] = lambda: _FakeAnalysisService(
        MealAnalysis()
    )

    body = client.post("/ai/analyze-meal", json=_body(), headers=_AUTH).json()

    assert body["nutritionalInfo"] is None
    assert body["alignment"] is None
    assert body["warnings"] == []


def test_to_command_maps_description_and_ingredients() -> None:
    request = AnalyzeMealRequest.model_validate(
        {
            "description": "Bowl",
            "ingredients": [{"name": "oats", "quantity": 80, "unit": "g", "protein": 12}],
        }
    )

    command = _to_command(request)

    assert command.description == "Bowl"
    [ingredient] = command.ingredients
    assert ingredient.name == "oats"
    assert ingredient.quantity == 80
    assert ingredient.unit == "g"
    assert ingredient.protein == 12


def test_projects_alignment_score_and_details() -> None:
    nutrition = AnalyzedNutrition(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    alignment = MealAligner(
        reference=MealReference(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    ).align(nutrition)
    app.dependency_overrides[get_meal_analysis_service] = lambda: _FakeAnalysisService(
        MealAnalysis(nutrition=nutrition, alignment=alignment)
    )

    body = client.post("/ai/analyze-meal", json=_body(), headers=_AUTH).json()

    assert body["alignment"]["score"] == 100.0
    assert "100" in body["alignment"]["details"]
