"""DPL-607: favorite-recipe use cases, against in-memory repositories (no MongoDB)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.commands import ListFavoritesQuery
from app.application.favorite_service import FavoriteService
from app.domain.errors import NotFoundError, RecipeDetailNotFoundError
from app.domain.favorite import Favorite
from app.domain.recipe import Ingredient, Recipe
from tests.fakes import InMemoryFavoriteRepository, InMemoryRecipeRepository

USER = "user-1"
OTHER = "user-2"


def _recipe(name: str) -> Recipe:
    return Recipe.create(name=name, servings=2, ingredients=[Ingredient(name="Water")])


@pytest.fixture
def recipes() -> InMemoryRecipeRepository:
    repo = InMemoryRecipeRepository()
    for name in ("Soup", "Salad", "Stew"):
        repo.add(_recipe(name))
    return repo


@pytest.fixture
def favorites() -> InMemoryFavoriteRepository:
    return InMemoryFavoriteRepository()


@pytest.fixture
def service(favorites, recipes) -> FavoriteService:
    return FavoriteService(favorites, recipes)


def _ids(recipes: InMemoryRecipeRepository) -> dict[str, str]:
    return {r.name: r.id for r in recipes.saved.values()}


def _save_at(
    favorites: InMemoryFavoriteRepository, user: str, recipe_id: str, minutes: int
) -> None:
    """Save a favorite with an explicit age, so ordering does not depend on the clock."""
    when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)
    favorites.add(Favorite(user_id=user, recipe_id=recipe_id, created_at=when))


def test_add_saves_a_catalog_recipe(service, favorites, recipes):
    soup = _ids(recipes)["Soup"]

    service.add_favorite(USER, soup)

    assert [f.recipe_id for f in favorites.list_for_user(USER)] == [soup]


def test_add_unknown_recipe_is_not_found(service, favorites):
    with pytest.raises(RecipeDetailNotFoundError) as excinfo:
        service.add_favorite(USER, "no-such-recipe")

    assert isinstance(excinfo.value, NotFoundError)
    assert favorites.saved == {}


def test_add_is_idempotent_and_keeps_the_first_timestamp(service, favorites, recipes):
    soup = _ids(recipes)["Soup"]
    service.add_favorite(USER, soup)
    first = favorites.list_for_user(USER)[0]

    service.add_favorite(USER, soup)

    saved = favorites.list_for_user(USER)
    assert len(saved) == 1
    assert saved[0].id == first.id
    assert saved[0].created_at == first.created_at


def test_remove_forgets_the_recipe(service, favorites, recipes):
    soup = _ids(recipes)["Soup"]
    service.add_favorite(USER, soup)

    service.remove_favorite(USER, soup)

    assert favorites.list_for_user(USER) == []


def test_remove_is_idempotent(service):
    service.remove_favorite(USER, "never-saved")
    service.remove_favorite(USER, "never-saved")


def test_list_returns_full_recipes_newest_first(service, favorites, recipes):
    ids = _ids(recipes)
    _save_at(favorites, USER, ids["Soup"], 0)
    _save_at(favorites, USER, ids["Stew"], 10)
    _save_at(favorites, USER, ids["Salad"], 5)

    result = service.list_favorites(ListFavoritesQuery(user_id=USER))

    assert [r.name for r in result] == ["Stew", "Salad", "Soup"]
    assert all(isinstance(r, Recipe) for r in result)


def test_list_is_scoped_to_the_caller(service, favorites, recipes):
    ids = _ids(recipes)
    service.add_favorite(USER, ids["Soup"])
    service.add_favorite(OTHER, ids["Stew"])

    mine = service.list_favorites(ListFavoritesQuery(user_id=USER))
    theirs = service.list_favorites(ListFavoritesQuery(user_id=OTHER))

    assert [r.name for r in mine] == ["Soup"]
    assert [r.name for r in theirs] == ["Stew"]


def test_one_user_removing_does_not_touch_another_users_favorite(service, recipes):
    soup = _ids(recipes)["Soup"]
    service.add_favorite(USER, soup)
    service.add_favorite(OTHER, soup)

    service.remove_favorite(USER, soup)

    assert service.list_favorites(ListFavoritesQuery(user_id=USER)) == []
    assert [r.id for r in service.list_favorites(ListFavoritesQuery(user_id=OTHER))] == [soup]


def test_list_pages_with_one_based_pages(service, favorites, recipes):
    ids = _ids(recipes)
    _save_at(favorites, USER, ids["Soup"], 0)
    _save_at(favorites, USER, ids["Salad"], 1)
    _save_at(favorites, USER, ids["Stew"], 2)

    first = service.list_favorites(ListFavoritesQuery(user_id=USER, page=1, limit=2))
    second = service.list_favorites(ListFavoritesQuery(user_id=USER, page=2, limit=2))

    assert [r.name for r in first] == ["Stew", "Salad"]
    assert [r.name for r in second] == ["Soup"]


def test_a_favorite_whose_recipe_left_the_catalog_is_skipped(service, favorites, recipes):
    ids = _ids(recipes)
    service.add_favorite(USER, ids["Soup"])
    service.add_favorite(USER, ids["Stew"])
    del recipes.saved[ids["Soup"]]

    result = service.list_favorites(ListFavoritesQuery(user_id=USER))

    assert [r.name for r in result] == ["Stew"]


def test_list_with_nothing_saved_is_empty(service):
    assert service.list_favorites(ListFavoritesQuery(user_id=USER)) == []
