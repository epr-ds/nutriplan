"""DPL-102 API tests for ``POST /meal-plans`` (Mongo-free via dependency overrides).

The service is overridden with an in-memory repository and the token verifier with a stub, so the
test exercises the real router, request/response models, auth dependency, and domain-error mapping
without MongoDB or network access.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_plan_service, get_token_verifier
from app.application.meal_plan_service import MealPlanService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.main import app
from tests.fakes import InMemoryMealPlanRepository

VALID_BODY = {
    "name": "Cutting",
    "startDate": "2026-01-01",
    "endDate": "2026-01-07",
    "dailyCalorieTarget": 2000,
}

GOOD_TOKEN = "good-token"


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


@pytest.fixture
def repo() -> InMemoryMealPlanRepository:
    return InMemoryMealPlanRepository()


@pytest.fixture
def principal() -> Principal:
    return Principal(user_id="user-123", email="a@b.com")


@pytest.fixture
def client(repo, principal):
    app.dependency_overrides[get_meal_plan_service] = lambda: MealPlanService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_returns_201_with_response_projection(client, repo):
    response = client.post("/meal-plans", json=VALID_BODY, headers=_auth())

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["name"] == "Cutting"
    assert data["startDate"] == "2026-01-01"
    assert data["endDate"] == "2026-01-07"
    assert data["dailyCalorieTarget"] == 2000
    assert data["meals"] == []
    assert "id" in data
    # Persisted and scoped to the authenticated caller.
    assert repo.get("user-123", data["id"]) is not None


def test_create_accepts_optional_targets(client):
    body = {
        **VALID_BODY,
        "macroTargets": {"proteinGrams": 150, "carbsGrams": 180, "fatGrams": 60},
        "dietaryType": "keto",
    }
    response = client.post("/meal-plans", json=body, headers=_auth())
    assert response.status_code == 201


def test_create_includes_summary_with_targets_and_empty_totals(client):
    body = {
        **VALID_BODY,
        "macroTargets": {"proteinGrams": 150, "carbsGrams": 180, "fatGrams": 60, "sugarGrams": 40},
    }
    response = client.post("/meal-plans", json=body, headers=_auth())

    assert response.status_code == 201
    summary = response.json()["nutritionalSummary"]
    # A fresh draft has no meals, so totals/averages are unknown (null), not zero.
    assert summary["total"]["calories"] is None
    assert summary["dailyAverage"]["calories"] is None
    # Targets reflect the requested calorie + macro goals.
    assert summary["targets"]["calories"] == 2000
    assert summary["targets"]["protein"] == 150
    assert summary["targets"]["carbs"] == 180
    assert summary["targets"]["fat"] == 60
    assert summary["targets"]["sugar"] == 40


def test_create_requires_authentication(client):
    response = client.post("/meal-plans", json=VALID_BODY)
    assert response.status_code == 401


def test_create_rejects_invalid_token(client):
    response = client.post("/meal-plans", json=VALID_BODY, headers=_auth("bogus"))
    assert response.status_code == 401


def test_create_rejects_end_before_start(client):
    body = {**VALID_BODY, "startDate": "2026-01-07", "endDate": "2026-01-01"}
    response = client.post("/meal-plans", json=body, headers=_auth())
    assert response.status_code == 422


def test_create_rejects_missing_required_field(client):
    body = {"startDate": "2026-01-01", "endDate": "2026-01-07", "dailyCalorieTarget": 2000}
    response = client.post("/meal-plans", json=body, headers=_auth())
    assert response.status_code == 422


def test_create_does_not_leak_user_id(client):
    response = client.post("/meal-plans", json=VALID_BODY, headers=_auth())
    assert "userId" not in response.json()
