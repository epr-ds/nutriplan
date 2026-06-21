"""DPL-104 API tests for ``GET /meal-plans/{planId}`` (Mongo-free via dependency overrides).

The service is overridden with an in-memory repository and the token verifier with a stub, so the
test exercises the real router, auth dependency, owner scoping and the full-detail projection
(including embedded meals) without MongoDB or network access.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_plan_service, get_token_verifier
from app.application.meal_plan_service import MealPlanService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import (
    MealPlan,
    MealPlanStatus,
    MealType,
    NutritionalInfo,
    PlannedMeal,
)
from app.main import app
from tests.fakes import InMemoryMealPlanRepository

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


def _seed(repo: InMemoryMealPlanRepository, user_id: str, *, with_meal: bool = False) -> MealPlan:
    meals = []
    if with_meal:
        meals = [
            PlannedMeal(
                meal_type=MealType.BREAKFAST,
                recipe_id="recipe-1",
                servings=1.5,
                day_index=0,
                nutritional_info=NutritionalInfo(calories=420, protein=30.0),
            )
        ]
    plan = MealPlan(
        user_id=user_id,
        name="Cutting",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=MealPlanStatus.ACTIVE,
        meals=meals,
    )
    repo.add(plan)
    return plan


def test_get_requires_authentication(client, repo, principal):
    plan = _seed(repo, principal.user_id)
    assert client.get(f"/meal-plans/{plan.id}").status_code == 401


def test_get_returns_full_meal_plan_with_meals(client, repo, principal):
    plan = _seed(repo, principal.user_id, with_meal=True)

    response = client.get(f"/meal-plans/{plan.id}", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == plan.id
    assert data["name"] == "Cutting"
    assert data["startDate"] == "2026-01-01"
    assert data["endDate"] == "2026-01-07"
    assert data["dailyCalorieTarget"] == 2000
    assert data["status"] == "active"
    # Full detail includes the embedded meals.
    assert len(data["meals"]) == 1
    meal = data["meals"][0]
    assert meal["mealType"] == "breakfast"
    assert meal["servings"] == 1.5
    assert meal["nutritionalInfo"]["calories"] == 420
    # Owner id is never exposed.
    assert "userId" not in data


def test_get_unknown_plan_returns_404(client):
    response = client.get("/meal-plans/00000000-0000-0000-0000-000000000000", headers=_auth())
    assert response.status_code == 404


def test_get_other_users_plan_returns_404_no_leakage(client, repo):
    # A plan that exists but is owned by someone else must be indistinguishable from missing.
    other = _seed(repo, "someone-else")

    response = client.get(f"/meal-plans/{other.id}", headers=_auth())

    assert response.status_code == 404
