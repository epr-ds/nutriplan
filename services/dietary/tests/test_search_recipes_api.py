"""DPL-202 API tests for ``GET /recipes`` (Mongo-free via dependency overrides).

The recipe service is overridden with an in-memory repository and the token verifier with a stub,
so the real router, auth guard, query-param parsing/validation and the ``RecipeResponse`` projection
are exercised without MongoDB or network access.
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


def _recipe(name, *, ingredients=(), calories=None, protein=None, diets=()):
    return Recipe.create(
        name=name,
        servings=2,
        ingredients=[Ingredient(name=i) for i in ingredients],
        nutritional_info=NutritionalInfo(calories=calories, protein=protein),
        dietary_types=list(diets),
    )


@pytest.fixture
def recipes() -> InMemoryRecipeRepository:
    repo = InMemoryRecipeRepository()
    repo.add(
        _recipe(
            "Oats",
            ingredients=["Rolled oats", "Milk"],
            calories=243,
            protein=9.9,
            diets=[DietaryType.VEGETARIAN],
        )
    )
    repo.add(
        _recipe(
            "Tofu Stir-Fry",
            ingredients=["Firm tofu", "Broccoli"],
            calories=228,
            protein=23.5,
            diets=[DietaryType.VEGAN, DietaryType.VEGETARIAN],
        )
    )
    repo.add(
        _recipe(
            "Chicken Bowl",
            ingredients=["Chicken breast", "Quinoa"],
            calories=550,
            protein=55.0,
            diets=[DietaryType.OMNIVORE],
        )
    )
    repo.add(
        _recipe(
            "Salmon",
            ingredients=["Salmon fillet", "Zucchini"],
            calories=473,
            protein=32.3,
            diets=[DietaryType.PALEO],
        )
    )
    return repo


@pytest.fixture
def principal() -> Principal:
    return Principal(user_id="user-123", email="a@b.com")


@pytest.fixture
def client(recipes, principal):
    app.dependency_overrides[get_recipe_service] = lambda: RecipeService(recipes)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _names(payload) -> list[str]:
    return [r["name"] for r in payload]


def test_search_requires_authentication(client):
    assert client.get("/recipes").status_code == 401


def test_empty_query_returns_all_name_sorted(client):
    response = client.get("/recipes", headers=_auth())
    assert response.status_code == 200
    assert _names(response.json()) == ["Chicken Bowl", "Oats", "Salmon", "Tofu Stir-Fry"]


def test_response_includes_dietary_types(client):
    payload = client.get("/recipes", headers=_auth()).json()
    tofu = next(r for r in payload if r["name"] == "Tofu Stir-Fry")
    assert tofu["dietaryTypes"] == ["vegan", "vegetarian"]


def test_filter_by_diet_type(client):
    payload = client.get("/recipes", params={"dietType": "vegan"}, headers=_auth()).json()
    assert _names(payload) == ["Tofu Stir-Fry"]


def test_filter_by_ingredients_requires_all_case_insensitive(client):
    payload = client.get(
        "/recipes",
        params=[("ingredients", "FIRM TOFU"), ("ingredients", "broccoli")],
        headers=_auth(),
    ).json()
    assert _names(payload) == ["Tofu Stir-Fry"]


def test_filter_by_max_calories(client):
    payload = client.get("/recipes", params={"maxCalories": 250}, headers=_auth()).json()
    assert _names(payload) == ["Oats", "Tofu Stir-Fry"]


def test_filter_by_min_protein(client):
    payload = client.get("/recipes", params={"minProtein": 30}, headers=_auth()).json()
    assert _names(payload) == ["Chicken Bowl", "Salmon"]


def test_pagination_is_stable(client):
    page1 = client.get("/recipes", params={"page": 1, "limit": 2}, headers=_auth()).json()
    page2 = client.get("/recipes", params={"page": 2, "limit": 2}, headers=_auth()).json()
    assert _names(page1) == ["Chicken Bowl", "Oats"]
    assert _names(page2) == ["Salmon", "Tofu Stir-Fry"]


def test_invalid_diet_type_returns_422(client):
    assert (
        client.get("/recipes", params={"dietType": "carnivore"}, headers=_auth()).status_code == 422
    )


def test_limit_over_cap_returns_422(client):
    assert client.get("/recipes", params={"limit": 101}, headers=_auth()).status_code == 422
