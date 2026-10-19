"""Favorite recipes API router (DPL-607)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, FavoriteServiceDep
from app.api.schemas import RecipeResponse
from app.application.commands import ListFavoritesQuery

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get(
    "",
    response_model=list[RecipeResponse],
    summary="List my favorite recipes",
)
def list_favorites(
    principal: CurrentPrincipal,
    service: FavoriteServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RecipeResponse]:
    """Return the caller's saved recipes, most recently saved first (DPL-607).

    Each item is the full catalog recipe, so the favorites screen can render it like a search
    result. The list is always the caller's own.
    """
    query = ListFavoritesQuery(user_id=principal.user_id, page=page, limit=limit)
    return [RecipeResponse.from_recipe(r) for r in service.list_favorites(query)]


@router.put(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Save a recipe as a favorite",
)
def add_favorite(
    recipe_id: str,
    principal: CurrentPrincipal,
    service: FavoriteServiceDep,
) -> Response:
    """Save a catalog recipe to the caller's favorites (DPL-607).

    Idempotent: saving a recipe that is already a favorite succeeds and changes nothing. An id that
    is not in the catalog returns ``404``.
    """
    service.add_favorite(principal.user_id, recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a recipe from my favorites",
)
def remove_favorite(
    recipe_id: str,
    principal: CurrentPrincipal,
    service: FavoriteServiceDep,
) -> Response:
    """Remove a recipe from the caller's favorites (DPL-607).

    Idempotent: removing a recipe that is not a favorite (or does not exist) also succeeds.
    """
    service.remove_favorite(principal.user_id, recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
