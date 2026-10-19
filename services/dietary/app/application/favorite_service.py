"""Application service (use cases) for favorite recipes (DPL-607).

A user saves catalog recipes to find them again. The service keeps the rules in one place:

* saving a recipe that is not in the catalog is a ``404`` (the recipe is the resource being
  addressed), and saving one that is already saved is a no-op, so the call is idempotent;
* removing is idempotent too: removing something that is not a favorite succeeds, so a client can
  retry or replay a toggle without having to know the server's state;
* the list is the caller's own, newest first, as full catalog recipes. A favorite whose recipe has
  since left the catalog is skipped rather than failing the whole list.

The ``user_id`` always comes from the authenticated principal, never from the request, so one user
can never read or change another's favorites.
"""

from __future__ import annotations

from app.application.commands import ListFavoritesQuery
from app.domain.errors import RecipeDetailNotFoundError
from app.domain.favorite import Favorite
from app.domain.recipe import Recipe
from app.domain.repositories import FavoriteRepository, RecipeRepository


class FavoriteService:
    """Orchestrates favorite-recipe use cases over the repository ports."""

    def __init__(self, favorites: FavoriteRepository, recipes: RecipeRepository) -> None:
        self._favorites = favorites
        self._recipes = recipes

    def add_favorite(self, user_id: str, recipe_id: str) -> None:
        """Save *recipe_id* for the caller, or raise if it is not in the catalog (idempotent)."""
        if self._recipes.get(recipe_id) is None:
            raise RecipeDetailNotFoundError(recipe_id)
        self._favorites.add(Favorite(user_id=user_id, recipe_id=recipe_id))

    def remove_favorite(self, user_id: str, recipe_id: str) -> None:
        """Forget *recipe_id* for the caller; succeeds even when it was not a favorite."""
        self._favorites.remove(user_id, recipe_id)

    def list_favorites(self, query: ListFavoritesQuery) -> list[Recipe]:
        """Return the caller's favorite recipes, most recently saved first, one page at a time."""
        skip = (query.page - 1) * query.limit
        saved = self._favorites.list_for_user(query.user_id, skip=skip, limit=query.limit)
        recipes = (self._recipes.get(favorite.recipe_id) for favorite in saved)
        return [recipe for recipe in recipes if recipe is not None]
