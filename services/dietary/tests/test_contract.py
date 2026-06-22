"""Provider contract tests (DPL-702).

Verify that the Dietary service's *actual* responses conform to the published
``contracts/dietary.openapi.yaml`` — every implemented operation is driven to each
response it documents (happy path + documented errors) and the real response is
validated against the contract with ``openapi-core``. A breaking change (renamed/
removed required field, changed type, drifted enum, undocumented status) makes a
test fail, which gates the PR in Backend CI.

The endpoints are exercised through the real routers/schemas but with the MongoDB
repositories and the JWT verifier swapped for in-memory doubles via FastAPI
``dependency_overrides`` — so the suite is deterministic and needs no database or
network, exactly like the other dietary API tests. The ``/ai/*`` operations are
documented for the AI service and are not implemented here, so they are not tested
(mirrors how Identity's contract tests skip its OAuth callback).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

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
from app.domain.dietary_types import DietaryType
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from app.main import app
from tests.fakes import InMemoryMealPlanRepository, InMemoryRecipeRepository

HOST = "http://localhost:8082"
GOOD_TOKEN = "good-token"
RECIPE_ID = "11111111-1111-1111-1111-111111111111"
MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _locate_spec() -> Path | None:
    if env := os.getenv("DIETARY_OPENAPI_SPEC"):
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    # Walk up from this file (…/services/dietary/tests) to the repo root, where the
    # contract lives at contracts/dietary.openapi.yaml. Also covers a /contracts mount.
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "contracts" / "dietary.openapi.yaml"
        if candidate.is_file():
            return candidate
    return None


_SPEC_PATH = _locate_spec()

if _SPEC_PATH is None:
    # In CI the contract is always checked out, so a miss means the gate is mis-wired —
    # fail loudly. Locally (e.g. a bare in-image run without the contract mounted) skip.
    if os.getenv("CI"):
        raise RuntimeError(
            "Provider contract tests could not locate contracts/dietary.openapi.yaml in CI. "
            "Set DIETARY_OPENAPI_SPEC or ensure the contract is checked out."
        )
    pytest.skip(
        "dietary.openapi.yaml not found; set DIETARY_OPENAPI_SPEC or mount /contracts",
        allow_module_level=True,
    )


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


def _full_recipe() -> Recipe:
    """A fully-populated catalog recipe (every optional field set) so the validated responses
    contain no stray nulls except the meal-level nutritionalInfo (which the contract allows)."""
    return Recipe.create(
        name="Overnight Oats with Berries",
        servings=2,
        description="No-cook oats soaked overnight with milk, chia and mixed berries.",
        ingredients=[
            Ingredient(
                name="Rolled oats",
                quantity=80.0,
                unit="g",
                calories=300,
                protein=10.5,
                carbs=54.0,
                fat=5.0,
                sugar=1.2,
            )
        ],
        instructions=["Combine oats, milk and chia.", "Top with berries.", "Chill overnight."],
        prep_time=5,
        cook_time=0,
        image_url="https://images.nutriplan.app/recipes/overnight-oats.jpg",
        nutritional_info=NutritionalInfo(calories=243, protein=9.9, carbs=38.1, fat=6.2, sugar=8.6),
        dietary_types=[DietaryType.VEGETARIAN, DietaryType.OMNIVORE],
    ).model_copy(update={"id": RECIPE_ID})


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    # The service emits errors as ``application/problem+json`` (RFC 7807, DPL-108); teach
    # openapi-core to deserialize that media type so error bodies are validated against Problem.
    config = Config(
        extra_media_type_deserializers={"application/problem+json": json.loads},
    )
    return OpenAPI.from_file_path(str(_SPEC_PATH), config=config)


@pytest.fixture
def client():
    plans = InMemoryMealPlanRepository()
    recipes = InMemoryRecipeRepository()
    recipes.add(_full_recipe())
    principal = Principal(user_id="user-123", email="contract@example.com")

    app.dependency_overrides[get_meal_plan_service] = lambda: MealPlanService(plans)
    app.dependency_overrides[get_meal_service] = lambda: MealService(plans, recipes)
    app.dependency_overrides[get_recipe_service] = lambda: RecipeService(recipes)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def assert_conforms(openapi: OpenAPI, method: str, path: str, response) -> None:
    """Validate a captured TestClient response against the contract for method+path."""
    content_type = response.headers.get("content-type", "application/json").split(";")[0].strip()
    request = MockRequest(host_url=HOST, method=method.lower(), path=path)
    mock_response = MockResponse(
        data=response.content,
        status_code=response.status_code,
        content_type=content_type,
    )
    openapi.validate_response(request, mock_response)


_AUTH = {"Authorization": f"Bearer {GOOD_TOKEN}"}


def _create_plan(client) -> dict:
    resp = client.post(
        "/meal-plans",
        json={
            "name": "Cutting",
            "startDate": "2026-01-01",
            "endDate": "2026-01-07",
            "dailyCalorieTarget": 2000,
        },
        headers=_AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_meal(client, plan_id: str):
    return client.post(
        f"/meal-plans/{plan_id}/meals",
        json={"mealType": "breakfast", "recipeId": RECIPE_ID, "servings": 1.5},
        headers=_AUTH,
    )


# --- Meal plans -------------------------------------------------------------


def test_create_meal_plan_conforms(openapi, client):
    resp = client.post(
        "/meal-plans",
        json={
            "name": "Cutting",
            "startDate": "2026-01-01",
            "endDate": "2026-01-07",
            "dailyCalorieTarget": 2000,
        },
        headers=_AUTH,
    )
    assert resp.status_code == 201
    assert_conforms(openapi, "post", "/meal-plans", resp)


def test_list_meal_plans_conforms(openapi, client):
    _create_plan(client)
    resp = client.get("/meal-plans", headers=_AUTH)
    assert resp.status_code == 200
    assert_conforms(openapi, "get", "/meal-plans", resp)


def test_get_meal_plan_conforms(openapi, client):
    plan = _create_plan(client)
    resp = client.get(f"/meal-plans/{plan['id']}", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["meals"] == []
    assert_conforms(openapi, "get", f"/meal-plans/{plan['id']}", resp)


def test_get_meal_plan_not_found_conforms(openapi, client):
    resp = client.get(f"/meal-plans/{MISSING_ID}", headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "get", f"/meal-plans/{MISSING_ID}", resp)


def test_update_status_conforms(openapi, client):
    plan = _create_plan(client)
    assert _add_meal(client, plan["id"]).status_code == 201
    resp = client.patch(f"/meal-plans/{plan['id']}", json={"status": "active"}, headers=_AUTH)
    assert resp.status_code == 200
    assert_conforms(openapi, "patch", f"/meal-plans/{plan['id']}", resp)


def test_update_status_not_found_conforms(openapi, client):
    resp = client.patch(f"/meal-plans/{MISSING_ID}", json={"status": "active"}, headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "patch", f"/meal-plans/{MISSING_ID}", resp)


def test_update_status_illegal_transition_conforms(openapi, client):
    plan = _create_plan(client)
    # draft -> completed is not an allowed transition (must activate first).
    resp = client.patch(f"/meal-plans/{plan['id']}", json={"status": "completed"}, headers=_AUTH)
    assert resp.status_code == 409
    assert_conforms(openapi, "patch", f"/meal-plans/{plan['id']}", resp)


def test_update_status_empty_activation_conforms(openapi, client):
    plan = _create_plan(client)
    # Activating a plan with no meals is a precondition failure (422).
    resp = client.patch(f"/meal-plans/{plan['id']}", json={"status": "active"}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "patch", f"/meal-plans/{plan['id']}", resp)


# --- Meals ------------------------------------------------------------------


def test_add_meal_conforms(openapi, client):
    plan = _create_plan(client)
    resp = _add_meal(client, plan["id"])
    assert resp.status_code == 201
    assert resp.json()["recipe"]["id"] == RECIPE_ID
    assert_conforms(openapi, "post", f"/meal-plans/{plan['id']}/meals", resp)


def test_add_meal_plan_not_found_conforms(openapi, client):
    resp = _add_meal(client, MISSING_ID)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", f"/meal-plans/{MISSING_ID}/meals", resp)


def test_add_meal_unknown_recipe_conforms(openapi, client):
    plan = _create_plan(client)
    resp = client.post(
        f"/meal-plans/{plan['id']}/meals",
        json={"mealType": "breakfast", "recipeId": "no-such-recipe", "servings": 1.0},
        headers=_AUTH,
    )
    assert resp.status_code == 422
    assert_conforms(openapi, "post", f"/meal-plans/{plan['id']}/meals", resp)


# --- Recipes ----------------------------------------------------------------


def test_search_recipes_conforms(openapi, client):
    resp = client.get("/recipes", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == RECIPE_ID
    assert_conforms(openapi, "get", "/recipes", resp)


# --- Auth (problem+json, DPL-108) -------------------------------------------


def test_unauthenticated_list_conforms(openapi, client):
    # No bearer at all: the auth dependency short-circuits with 401 before any handler,
    # and the body must be an RFC 7807 problem document documented on the operation.
    resp = client.get("/meal-plans")
    assert resp.status_code == 401
    assert resp.headers["content-type"].split(";")[0].strip() == "application/problem+json"
    assert_conforms(openapi, "get", "/meal-plans", resp)


def test_unauthenticated_search_recipes_conforms(openapi, client):
    resp = client.get("/recipes")
    assert resp.status_code == 401
    assert_conforms(openapi, "get", "/recipes", resp)
