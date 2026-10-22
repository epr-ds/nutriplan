"""The QA test harness (DPL-701): an ephemeral Dietary database with seeded plans and recipes.

Run with ``DIETARY_TEST_DB=mongo`` to bring MongoDB up through Testcontainers (as the
``dietary-testcontainers`` CI job does); without it the same tests use ``DIETARY_MONGO_URL``. They
prove the harness itself: the database is the one asked for, the seed fixtures pass the
collections' ``$jsonSchema`` validators and read back through the repositories, and the same
fixtures serve an integration test through the real API and Mongo repositories whose responses
are checked against ``contracts/dietary.openapi.yaml`` like the provider contract tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

from app.api.deps import get_token_verifier
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.db.mongo import meal_plans, recipes
from app.domain.nutrition import summarize_plan_nutrition
from app.main import app
from app.repositories.mongo_meal_plan_repository import MongoMealPlanRepository
from app.repositories.mongo_recipe_repository import MongoRecipeRepository
from tests.seed import SEED_MEAL_TYPES, SEED_USER_ID, seed_catalog

HOST = "http://localhost:8082"
TOKEN = "harness-token"


def test_the_database_is_the_one_asked_for(db_source, mongo_db):
    assert mongo_db.client.admin.command("ping")["ok"] == 1
    if os.environ.get("DIETARY_TEST_DB", "").lower() in {"mongo", "testcontainers"}:
        assert db_source == "testcontainers"
    else:
        assert db_source in {"env", "default"}


def test_seeded_recipes_are_stored_and_read_back(mongo_db, seeded_recipes):
    assert recipes(mongo_db).count_documents({}) == len(seeded_recipes) > 0
    repository = MongoRecipeRepository(recipes(mongo_db))
    for recipe in seeded_recipes:
        stored = repository.get(recipe.id)
        assert stored is not None
        assert stored.name == recipe.name


def test_seeding_the_catalog_twice_does_not_duplicate_it(mongo_db, seeded_recipes):
    seed_catalog(mongo_db)

    assert recipes(mongo_db).count_documents({}) == len(seeded_recipes)


def test_the_seeded_plan_passes_the_schema_and_reads_back(mongo_db, seeded_plan, seeded_recipes):
    stored = MongoMealPlanRepository(meal_plans(mongo_db)).get(SEED_USER_ID, seeded_plan.id)

    assert stored is not None
    assert stored.status == "draft"
    assert [meal.meal_type for meal in stored.meals] == list(SEED_MEAL_TYPES)
    assert [meal.day_index for meal in stored.meals] == [0, 1, 2]
    assert [meal.recipe_id for meal in stored.meals] == [r.id for r in seeded_recipes[:3]]
    assert all(meal.nutritional_info is not None for meal in stored.meals)
    summary = summarize_plan_nutrition(stored)
    assert summary.total.calories is not None and summary.total.calories > 0


def test_the_seeded_plan_belongs_only_to_its_user(mongo_db, seeded_plan):
    repository = MongoMealPlanRepository(meal_plans(mongo_db))

    assert repository.get("someone-else", seeded_plan.id) is None


# --- The same fixtures through the real API (integration + contract) --------------------


class _Verifier:
    def verify(self, token: str) -> Principal:
        if token != TOKEN:
            raise InvalidTokenError("unknown token")
        return Principal(user_id=SEED_USER_ID, email="harness@example.com")


def _spec_path() -> Path | None:
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "contracts" / "dietary.openapi.yaml"
        if candidate.is_file():
            return candidate
    return None


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    path = _spec_path()
    if path is None:
        pytest.skip("contracts/dietary.openapi.yaml not found")
    config = Config(extra_media_type_deserializers={"application/problem+json": json.loads})
    return OpenAPI.from_file_path(str(path), config=config)


@pytest.fixture
def api(client):
    # Only the token check is replaced: the services use the real Mongo repositories, which
    # read the same throwaway database as ``mongo_db``.
    app.dependency_overrides[get_token_verifier] = lambda: _Verifier()
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _conforms(openapi: OpenAPI, path: str, response) -> None:
    content_type = response.headers.get("content-type", "application/json").split(";")[0].strip()
    request = MockRequest(host_url=HOST, method="get", path=path)
    mock_response = MockResponse(
        data=response.content, status_code=response.status_code, content_type=content_type
    )
    openapi.validate_response(request, mock_response)


def test_the_seeded_plan_is_served_by_the_api_as_the_contract_says(openapi, api, seeded_plan):
    path = f"/meal-plans/{seeded_plan.id}"
    response = api.get(path, headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == seeded_plan.id
    assert [meal["mealType"] for meal in body["meals"]] == [t.value for t in SEED_MEAL_TYPES]
    assert body["nutritionalSummary"]["total"]["calories"] > 0
    _conforms(openapi, path, response)


def test_the_seeded_recipes_are_served_by_the_api_as_the_contract_says(
    openapi, api, seeded_recipes
):
    path = f"/recipes/{seeded_recipes[0].id}"
    response = api.get(path, headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200, response.text
    assert response.json()["name"] == seeded_recipes[0].name
    _conforms(openapi, path, response)
