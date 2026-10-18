"""DPL-203 API tests for ``GET /recipes/{recipeId}`` (Mongo-free via dependency overrides).

The recipe service is overridden with an in-memory repository and the token verifier with a stub,
so the real router, auth guard, path-param parsing and the ``RecipeResponse`` projection are
exercised without MongoDB or network access.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_recipe_service, get_token_verifier
from app.application.recipe_service import RecipeService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.dietary_types import DietaryType
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe
from app.main import app
from tests.fakes import InMemoryRecipeRepository

GOOD_TOKEN = "good-token"


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


def _full_recipe() -> Recipe:
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
    )


@pytest.fixture
def recipe() -> Recipe:
    return _full_recipe()


@pytest.fixture
def client(recipe) -> TestClient:
    repo = InMemoryRecipeRepository()
    repo.add(recipe)
    principal = Principal(user_id="user-123", email="a@b.com")
    app.dependency_overrides[get_recipe_service] = lambda: RecipeService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_recipe_requires_authentication(client):
    assert client.get("/recipes/any-id").status_code == 401


def test_get_recipe_returns_full_detail(client, recipe):
    response = client.get(f"/recipes/{recipe.id}", headers=_auth())
    assert response.status_code == 200

    body = response.json()
    assert body["id"] == recipe.id
    assert body["name"] == "Overnight Oats with Berries"
    assert body["description"] == "No-cook oats soaked overnight with milk, chia and mixed berries."
    assert body["ingredients"][0]["name"] == "Rolled oats"
    assert body["ingredients"][0]["quantity"] == 80.0
    assert body["instructions"] == [
        "Combine oats, milk and chia.",
        "Top with berries.",
        "Chill overnight.",
    ]
    assert body["prepTime"] == 5
    assert body["cookTime"] == 0
    assert body["nutritionalInfo"]["calories"] == 243
    assert body["nutritionalInfo"]["protein"] == 9.9
    assert body["dietaryTypes"] == ["vegetarian", "omnivore"]


def test_get_recipe_unknown_id_returns_404_problem(client):
    response = client.get("/recipes/no-such-recipe", headers=_auth())
    assert response.status_code == 404
    assert response.headers["content-type"].split(";")[0].strip() == "application/problem+json"
    assert response.json()["status"] == 404
