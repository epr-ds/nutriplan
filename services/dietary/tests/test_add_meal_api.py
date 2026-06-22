"""DPL-105 API tests for ``POST /meal-plans/{planId}/meals`` (Mongo-free via overrides).

The add-meal service is overridden with in-memory plan + recipe repositories and the token verifier
with a stub, exercising the real router, auth, owner scoping, recipe validation and the meal
projection (with its embedded recipe) without MongoDB or network access.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_service, get_token_verifier
from app.application.meal_service import MealService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import MealPlan, MealPlanStatus
from app.domain.recipe import NutritionalInfo, Recipe
from app.main import app
from tests.fakes import InMemoryMealPlanRepository, InMemoryRecipeRepository

GOOD_TOKEN = "good-token"
RECIPE_ID = "11111111-1111-1111-1111-111111111111"


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


@pytest.fixture
def plans() -> InMemoryMealPlanRepository:
    return InMemoryMealPlanRepository()


@pytest.fixture
def recipes() -> InMemoryRecipeRepository:
    repo = InMemoryRecipeRepository()
    repo.add(
        Recipe.create(
            name="Protein Oats",
            servings=2,
            nutritional_info=NutritionalInfo(calories=420, protein=30.0),
        ).model_copy(update={"id": RECIPE_ID})
    )
    return repo


@pytest.fixture
def principal() -> Principal:
    return Principal(user_id="user-123", email="a@b.com")


@pytest.fixture
def client(plans, recipes, principal):
    app.dependency_overrides[get_meal_service] = lambda: MealService(plans, recipes)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_plan(repo: InMemoryMealPlanRepository, user_id: str) -> MealPlan:
    plan = MealPlan(
        user_id=user_id,
        name="Cutting",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=MealPlanStatus.DRAFT,
    )
    repo.add(plan)
    return plan


def _body(*, recipe_id: str = RECIPE_ID, servings: float = 1.5) -> dict:
    return {"mealType": "breakfast", "recipeId": recipe_id, "servings": servings}


def test_add_meal_requires_authentication(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    assert client.post(f"/meal-plans/{plan.id}/meals", json=_body()).status_code == 401


def test_add_meal_returns_201_with_recipe(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)

    response = client.post(f"/meal-plans/{plan.id}/meals", json=_body(), headers=_auth())

    assert response.status_code == 201
    data = response.json()
    assert data["mealType"] == "breakfast"
    assert data["servings"] == 1.5
    assert data["id"]
    assert data["recipe"]["id"] == RECIPE_ID
    assert data["recipe"]["name"] == "Protein Oats"
    assert data["recipe"]["nutritionalInfo"]["calories"] == 420
    # The mutated plan now carries the meal.
    assert len(plans.get(principal.user_id, plan.id).meals) == 1


def test_add_meal_response_includes_computed_nutrition(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)

    response = client.post(
        f"/meal-plans/{plan.id}/meals", json=_body(servings=1.5), headers=_auth()
    )

    assert response.status_code == 201
    # Per-serving 420 cal / 30 g protein scaled to 1.5 servings (DPL-301).
    info = response.json()["nutritionalInfo"]
    assert info["calories"] == 630
    assert info["protein"] == 45.0


def test_add_meal_unknown_recipe_returns_422(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)

    response = client.post(
        f"/meal-plans/{plan.id}/meals",
        json=_body(recipe_id="no-such-recipe"),
        headers=_auth(),
    )

    assert response.status_code == 422
    assert plans.get(principal.user_id, plan.id).meals == []


def test_add_meal_unknown_plan_returns_404(client):
    response = client.post(
        "/meal-plans/00000000-0000-0000-0000-000000000000/meals",
        json=_body(),
        headers=_auth(),
    )
    assert response.status_code == 404


def test_add_meal_other_users_plan_returns_404(client, plans):
    other = _seed_plan(plans, "someone-else")

    response = client.post(f"/meal-plans/{other.id}/meals", json=_body(), headers=_auth())

    assert response.status_code == 404
    assert plans.get("someone-else", other.id).meals == []


@pytest.mark.parametrize("servings", [0, -1])
def test_add_meal_non_positive_servings_returns_422(client, plans, principal, servings):
    plan = _seed_plan(plans, principal.user_id)

    response = client.post(
        f"/meal-plans/{plan.id}/meals",
        json=_body(servings=servings),
        headers=_auth(),
    )

    assert response.status_code == 422
    assert plans.get(principal.user_id, plan.id).meals == []
