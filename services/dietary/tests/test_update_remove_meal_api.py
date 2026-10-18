"""DPL-107 API tests for ``PATCH``/``DELETE /meal-plans/{planId}/meals/{mealId}`` (Mongo-free).

Real routers, auth, owner scoping, request validation and the meal projection are exercised with
in-memory plan/recipe repositories and a stub token verifier — no MongoDB or network.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_plan_service, get_meal_service, get_token_verifier
from app.application.meal_plan_service import MealPlanService
from app.application.meal_service import MealService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import MealPlan, MealPlanStatus, MealType
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
    app.dependency_overrides[get_meal_plan_service] = lambda: MealPlanService(plans)
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


def _add_meal(client, plan_id: str, servings: float = 1.0) -> dict:
    response = client.post(
        f"/meal-plans/{plan_id}/meals",
        json={"mealType": "breakfast", "recipeId": RECIPE_ID, "servings": servings},
        headers=_auth(),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- PATCH ------------------------------------------------------------------


def test_update_meal_requires_authentication(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)
    assert (
        client.patch(f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"servings": 2}).status_code
        == 401
    )


def test_update_meal_servings_recomputes_nutrition(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id, servings=1.0)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"servings": 1.5}, headers=_auth()
    )

    assert response.status_code == 200
    data = response.json()
    assert data["servings"] == 1.5
    assert data["nutritionalInfo"]["calories"] == 630
    assert data["nutritionalInfo"]["protein"] == 45.0
    assert data["recipe"]["id"] == RECIPE_ID


def test_update_meal_assigns_day_index(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"dayIndex": 5}, headers=_auth()
    )

    assert response.status_code == 200
    assert response.json()["dayIndex"] == 5
    assert plans.get(principal.user_id, plan.id).find_meal(meal["id"]).day_index == 5


def test_update_meal_records_satisfaction(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}",
        json={"satisfactionLevel": 4},
        headers=_auth(),
    )

    assert response.status_code == 200
    assert response.json()["satisfactionLevel"] == 4
    assert plans.get(principal.user_id, plan.id).find_meal(meal["id"]).satisfaction_level == 4

    detail = client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()
    assert detail["meals"][0]["satisfactionLevel"] == 4
    assert detail["meals"][0]["dayIndex"] is None


@pytest.mark.parametrize("level", [0, 6])
def test_update_meal_satisfaction_out_of_range_returns_422(client, plans, principal, level):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}",
        json={"satisfactionLevel": level},
        headers=_auth(),
    )

    assert response.status_code == 422
    assert plans.get(principal.user_id, plan.id).find_meal(meal["id"]).satisfaction_level is None


def test_update_meal_servings_and_satisfaction_together(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id, servings=1.0)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}",
        json={"servings": 2.0, "satisfactionLevel": 3},
        headers=_auth(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["servings"] == 2.0
    assert data["satisfactionLevel"] == 3
    assert data["nutritionalInfo"]["calories"] == 840


def test_update_meal_day_out_of_range_returns_422(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"dayIndex": 7}, headers=_auth()
    )

    assert response.status_code == 422
    assert plans.get(principal.user_id, plan.id).find_meal(meal["id"]).day_index is None


def test_update_meal_empty_body_returns_422(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(f"/meal-plans/{plan.id}/meals/{meal['id']}", json={}, headers=_auth())

    assert response.status_code == 422


@pytest.mark.parametrize("servings", [0, -1])
def test_update_meal_non_positive_servings_returns_422(client, plans, principal, servings):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"servings": servings}, headers=_auth()
    )

    assert response.status_code == 422


def test_update_meal_unknown_meal_returns_404(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)

    response = client.patch(
        f"/meal-plans/{plan.id}/meals/00000000-0000-0000-0000-000000000000",
        json={"servings": 2},
        headers=_auth(),
    )

    assert response.status_code == 404


def test_update_meal_unknown_plan_returns_404(client):
    response = client.patch(
        "/meal-plans/00000000-0000-0000-0000-000000000000/meals/whatever",
        json={"servings": 2},
        headers=_auth(),
    )
    assert response.status_code == 404


def test_update_meal_other_users_plan_returns_404(client, plans):
    other = _seed_plan(plans, "someone-else")
    other.add_meal(meal_type=MealType.BREAKFAST, recipe_id=RECIPE_ID, servings=1.0)
    meal_id = other.meals[0].id

    response = client.patch(
        f"/meal-plans/{other.id}/meals/{meal_id}", json={"servings": 2}, headers=_auth()
    )

    assert response.status_code == 404


# --- DELETE ----------------------------------------------------------------


def test_remove_meal_requires_authentication(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)
    assert client.delete(f"/meal-plans/{plan.id}/meals/{meal['id']}").status_code == 401


def test_remove_meal_returns_204_and_drops_it(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id)

    response = client.delete(f"/meal-plans/{plan.id}/meals/{meal['id']}", headers=_auth())

    assert response.status_code == 204
    assert response.content == b""
    assert plans.get(principal.user_id, plan.id).meals == []


def test_remove_meal_unknown_meal_returns_404(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)

    response = client.delete(
        f"/meal-plans/{plan.id}/meals/00000000-0000-0000-0000-000000000000", headers=_auth()
    )

    assert response.status_code == 404


def test_remove_meal_unknown_plan_returns_404(client):
    response = client.delete(
        "/meal-plans/00000000-0000-0000-0000-000000000000/meals/whatever", headers=_auth()
    )
    assert response.status_code == 404


# --- Summary is recomputed after edit / remove (DPL-302 x DPL-107) -----------


def test_summary_reflects_update_then_remove(client, plans, principal):
    plan = _seed_plan(plans, principal.user_id)
    meal = _add_meal(client, plan.id, servings=1.0)

    first = client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()
    assert first["nutritionalSummary"]["total"]["calories"] == 420

    client.patch(
        f"/meal-plans/{plan.id}/meals/{meal['id']}", json={"servings": 2.0}, headers=_auth()
    )
    after_edit = client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()
    assert after_edit["nutritionalSummary"]["total"]["calories"] == 840

    client.delete(f"/meal-plans/{plan.id}/meals/{meal['id']}", headers=_auth())
    after_remove = client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()
    # No meals left => nothing measured, which is null (unknown), not zero (DPL-301/302).
    assert after_remove["nutritionalSummary"]["total"]["calories"] is None
    assert after_remove["meals"] == []
