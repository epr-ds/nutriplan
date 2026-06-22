"""DPL-108 API tests for the RFC 7807 ``application/problem+json`` error model.

Every 4xx/5xx response from the Dietary API must be a problem document with a single, predictable
shape (``type``/``title``/``status`` plus an ``instance``). These tests exercise the real routers,
auth dependency and owner scoping (Mongo-free via dependency overrides) and assert the *transport*
contract of errors:

* unauthenticated / invalid-token  -> 401 problem+json (+ ``WWW-Authenticate: Bearer``)
* a missing **or** cross-user plan  -> 404 problem+json, indistinguishable (no ownership leak)
* an illegal lifecycle transition   -> 409 problem+json
* a domain precondition / bad ref   -> 422 problem+json
* request/query validation failure  -> 422 problem+json carrying an ``errors`` array
* success responses stay ``application/json`` (the problem media type is errors-only)
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_meal_plan_service,
    get_meal_service,
    get_recipe_service,
    get_token_verifier,
)
from app.application.meal_plan_service import MealPlanService
from app.application.meal_service import MealService
from app.application.recipe_service import RecipeService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import MealPlan, MealPlanStatus, MealType, PlannedMeal
from app.domain.recipe import Recipe
from app.main import app
from tests.fakes import InMemoryMealPlanRepository, InMemoryRecipeRepository

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
MISSING_ID = "00000000-0000-0000-0000-000000000000"


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
    repo.add(Recipe.create(name="Oatmeal", servings=1).model_copy(update={"id": "recipe-1"}))
    return repo


@pytest.fixture
def principal() -> Principal:
    return Principal(user_id="user-123", email="a@b.com")


@pytest.fixture
def client(plans, recipes, principal):
    app.dependency_overrides[get_meal_plan_service] = lambda: MealPlanService(plans)
    app.dependency_overrides[get_meal_service] = lambda: MealService(plans, recipes)
    app.dependency_overrides[get_recipe_service] = lambda: RecipeService(recipes)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(
    repo: InMemoryMealPlanRepository,
    user_id: str,
    *,
    status: MealPlanStatus = MealPlanStatus.DRAFT,
    with_meal: bool = True,
) -> MealPlan:
    plan = MealPlan(
        user_id=user_id,
        name="Cutting",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=status,
        meals=[PlannedMeal(meal_type=MealType.BREAKFAST, recipe_id="recipe-1", servings=1.0)]
        if with_meal
        else [],
    )
    repo.add(plan)
    return plan


def _assert_problem(response, status_code: int, title: str) -> dict:
    assert response.status_code == status_code
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == title
    assert body["status"] == status_code
    return body


# --- 401 --------------------------------------------------------------------


def test_unauthenticated_request_returns_problem_json(client, plans, principal):
    plan = _seed(plans, principal.user_id)

    response = client.get(f"/meal-plans/{plan.id}")

    body = _assert_problem(response, 401, "Unauthorized")
    assert body["instance"] == f"/meal-plans/{plan.id}"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_invalid_token_returns_problem_json(client, plans, principal):
    plan = _seed(plans, principal.user_id)

    response = client.get(f"/meal-plans/{plan.id}", headers=_auth("bogus"))

    _assert_problem(response, 401, "Unauthorized")
    assert response.headers.get("www-authenticate") == "Bearer"


# --- 404 (AC2: missing and cross-user are indistinguishable) ----------------


def test_missing_plan_returns_404_problem_json(client):
    response = client.get(f"/meal-plans/{MISSING_ID}", headers=_auth())

    body = _assert_problem(response, 404, "Not Found")
    assert body["instance"] == f"/meal-plans/{MISSING_ID}"


def test_cross_user_plan_returns_404_problem_json_without_leak(client, plans):
    # A plan that exists but belongs to someone else must look exactly like a missing one.
    other = _seed(plans, "someone-else")

    missing = client.get(f"/meal-plans/{MISSING_ID}", headers=_auth())
    unowned = client.get(f"/meal-plans/{other.id}", headers=_auth())

    _assert_problem(missing, 404, "Not Found")
    unowned_body = _assert_problem(unowned, 404, "Not Found")
    # No ownership/existence leak: same status, same title, and the detail never says "forbidden".
    assert "forbidden" not in unowned_body.get("detail", "").lower()
    assert "someone-else" not in unowned_body.get("detail", "")


# --- 409 / 422 (domain) -----------------------------------------------------


def test_illegal_transition_returns_409_problem_json(client, plans, principal):
    plan = _seed(plans, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=True)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "completed"}, headers=_auth())

    _assert_problem(response, 409, "Conflict")


def test_empty_plan_activation_returns_422_problem_json(client, plans, principal):
    plan = _seed(plans, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=False)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "active"}, headers=_auth())

    _assert_problem(response, 422, "Unprocessable Entity")


def test_unknown_recipe_returns_422_problem_json(client, plans, principal):
    plan = _seed(plans, principal.user_id)

    response = client.post(
        f"/meal-plans/{plan.id}/meals",
        json={"mealType": "breakfast", "recipeId": "no-such-recipe", "servings": 1.0},
        headers=_auth(),
    )

    _assert_problem(response, 422, "Unprocessable Entity")


# --- 422 (request/query validation, with errors[] extension) ----------------


def test_request_validation_returns_422_problem_json_with_errors(client, plans, principal):
    plan = _seed(plans, principal.user_id, with_meal=True)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "archived"}, headers=_auth())

    body = _assert_problem(response, 422, "Unprocessable Entity")
    assert body["detail"] == "Request validation failed"
    assert isinstance(body["errors"], list) and body["errors"]
    first = body["errors"][0]
    assert {"loc", "msg", "type"} <= set(first)


def test_query_validation_returns_422_problem_json(client):
    # dietType is constrained to a known enum; an unknown value is a query-validation failure.
    response = client.get("/recipes", params={"dietType": "carnivore"}, headers=_auth())

    body = _assert_problem(response, 422, "Unprocessable Entity")
    assert isinstance(body["errors"], list) and body["errors"]


# --- success stays application/json -----------------------------------------


def test_success_response_is_plain_json(client, plans, principal):
    plan = _seed(plans, principal.user_id)

    response = client.get(f"/meal-plans/{plan.id}", headers=_auth())

    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0].strip() == "application/json"
