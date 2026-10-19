"""DPL-607 API tests for ``/favorites`` (Mongo-free via dependency overrides).

The favorite service is built on in-memory repositories and the token verifier is a stub with two
users, so the real router, auth guard, status codes and ``RecipeResponse`` projection are exercised
without MongoDB or network access.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_favorite_service, get_token_verifier
from app.application.favorite_service import FavoriteService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.recipe import Ingredient, Recipe
from app.main import app
from tests.fakes import InMemoryFavoriteRepository, InMemoryRecipeRepository

ALICE = "alice-token"
BOB = "bob-token"


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


def _recipe(name: str) -> Recipe:
    return Recipe.create(name=name, servings=2, ingredients=[Ingredient(name="Water")])


@pytest.fixture
def soup() -> Recipe:
    return _recipe("Soup")


@pytest.fixture
def stew() -> Recipe:
    return _recipe("Stew")


@pytest.fixture
def client(soup, stew) -> TestClient:
    recipes = InMemoryRecipeRepository()
    recipes.add(soup)
    recipes.add(stew)
    favorites = InMemoryFavoriteRepository()
    verifier = StubVerifier(
        {
            ALICE: Principal(user_id="alice", email="a@b.com"),
            BOB: Principal(user_id="bob", email="b@b.com"),
        }
    )
    app.dependency_overrides[get_favorite_service] = lambda: FavoriteService(favorites, recipes)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = ALICE) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_every_operation_requires_authentication(client, soup):
    assert client.get("/favorites").status_code == 401
    assert client.put(f"/favorites/{soup.id}").status_code == 401
    assert client.delete(f"/favorites/{soup.id}").status_code == 401


def test_a_bad_token_is_rejected(client):
    assert client.get("/favorites", headers=_auth("forged")).status_code == 401


def test_the_list_starts_empty(client):
    response = client.get("/favorites", headers=_auth())

    assert response.status_code == 200
    assert response.json() == []


def test_saving_a_recipe_returns_204_with_no_body_and_lists_it(client, soup):
    saved = client.put(f"/favorites/{soup.id}", headers=_auth())
    assert saved.status_code == 204
    assert saved.content == b""

    listed = client.get("/favorites", headers=_auth())
    assert listed.status_code == 200
    body = listed.json()
    assert [r["id"] for r in body] == [soup.id]
    # The full recipe is returned, so it can be drawn like a search result.
    assert body[0]["name"] == "Soup"
    assert body[0]["ingredients"][0]["name"] == "Water"


def test_saving_twice_is_idempotent(client, soup):
    assert client.put(f"/favorites/{soup.id}", headers=_auth()).status_code == 204
    assert client.put(f"/favorites/{soup.id}", headers=_auth()).status_code == 204

    assert len(client.get("/favorites", headers=_auth()).json()) == 1


def test_saving_an_unknown_recipe_is_a_404_problem(client):
    response = client.put("/favorites/no-such-recipe", headers=_auth())

    assert response.status_code == 404
    assert response.headers["content-type"].split(";")[0].strip() == "application/problem+json"
    assert response.json()["status"] == 404


def test_removing_a_favorite_returns_204_and_drops_it(client, soup):
    client.put(f"/favorites/{soup.id}", headers=_auth())

    removed = client.delete(f"/favorites/{soup.id}", headers=_auth())

    assert removed.status_code == 204
    assert client.get("/favorites", headers=_auth()).json() == []


def test_removing_something_that_is_not_a_favorite_still_succeeds(client):
    assert client.delete("/favorites/never-saved", headers=_auth()).status_code == 204


def test_favorites_are_private_to_each_user(client, soup, stew):
    client.put(f"/favorites/{soup.id}", headers=_auth(ALICE))
    client.put(f"/favorites/{stew.id}", headers=_auth(BOB))

    alice = [r["id"] for r in client.get("/favorites", headers=_auth(ALICE)).json()]
    bob = [r["id"] for r in client.get("/favorites", headers=_auth(BOB)).json()]

    assert alice == [soup.id]
    assert bob == [stew.id]


def test_one_user_removing_does_not_remove_anothers_favorite(client, soup):
    client.put(f"/favorites/{soup.id}", headers=_auth(ALICE))
    client.put(f"/favorites/{soup.id}", headers=_auth(BOB))

    client.delete(f"/favorites/{soup.id}", headers=_auth(ALICE))

    assert client.get("/favorites", headers=_auth(ALICE)).json() == []
    assert [r["id"] for r in client.get("/favorites", headers=_auth(BOB)).json()] == [soup.id]


def test_the_list_is_newest_first(client, soup, stew):
    client.put(f"/favorites/{soup.id}", headers=_auth())
    client.put(f"/favorites/{stew.id}", headers=_auth())

    ids = [r["id"] for r in client.get("/favorites", headers=_auth()).json()]

    assert ids == [stew.id, soup.id]


def test_the_list_pages(client, soup, stew):
    client.put(f"/favorites/{soup.id}", headers=_auth())
    client.put(f"/favorites/{stew.id}", headers=_auth())

    first = client.get("/favorites", params={"page": 1, "limit": 1}, headers=_auth()).json()
    second = client.get("/favorites", params={"page": 2, "limit": 1}, headers=_auth()).json()
    beyond = client.get("/favorites", params={"page": 3, "limit": 1}, headers=_auth()).json()

    assert [r["id"] for r in first] == [stew.id]
    assert [r["id"] for r in second] == [soup.id]
    assert beyond == []


@pytest.mark.parametrize("params", [{"page": 0}, {"limit": 0}, {"limit": 101}, {"page": "x"}])
def test_bad_paging_parameters_are_a_422(client, params):
    response = client.get("/favorites", params=params, headers=_auth())

    assert response.status_code == 422
    assert response.headers["content-type"].split(";")[0].strip() == "application/problem+json"
