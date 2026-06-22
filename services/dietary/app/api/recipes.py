"""Recipes API router (DPL-202)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, RecipeServiceDep
from app.api.schemas import RecipeResponse
from app.application.commands import SearchRecipesQuery
from app.domain.dietary_types import DietaryType

router = APIRouter(prefix="/recipes", tags=["Recipes"])


@router.get(
    "",
    response_model=list[RecipeResponse],
    summary="Search the recipe catalog",
)
def search_recipes(
    principal: CurrentPrincipal,
    service: RecipeServiceDep,
    ingredients: Annotated[list[str] | None, Query()] = None,
    diet_type: Annotated[DietaryType | None, Query(alias="dietType")] = None,
    max_calories: Annotated[int | None, Query(alias="maxCalories", ge=0)] = None,
    min_protein: Annotated[float | None, Query(alias="minProtein", ge=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RecipeResponse]:
    """Search the global recipe catalog with optional filters + pagination (DPL-202).

    All filters combine with AND: ``ingredients`` requires the recipe to contain every named
    ingredient (case-insensitive), ``dietType`` matches a declared compatible diet, and
    ``maxCalories``/``minProtein`` bound the per-serving nutrition. An empty or over-broad query is
    handled gracefully — results are ordered deterministically and capped by ``limit`` so paging is
    stable. Requires authentication; the catalog itself is global (not owner-scoped).
    """
    query = SearchRecipesQuery(
        ingredients=tuple(ingredients) if ingredients else (),
        diet_type=diet_type,
        max_calories=max_calories,
        min_protein=min_protein,
        page=page,
        limit=limit,
    )
    found = service.search_recipes(query)
    return [RecipeResponse.from_recipe(r) for r in found]
