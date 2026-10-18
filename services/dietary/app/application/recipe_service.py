"""Application service (use cases) for the recipe catalog (DPL-202).

The catalog is a global, read-mostly resource (not owner-scoped), so this service is a thin use-case
layer over the :class:`~app.domain.repositories.RecipeRepository` port: it translates the
``SearchRecipesQuery`` DTO (notably 1-based ``page`` -> ``skip`` offset) and delegates the actual
filtering + ordering to the repository, which can use its indexes. The repository is injected
(constructor injection) so the service is agnostic of MongoDB and unit-testable against a double.
"""

from __future__ import annotations

from app.application.commands import SearchRecipesQuery
from app.domain.errors import RecipeDetailNotFoundError
from app.domain.recipe import Recipe
from app.domain.repositories import RecipeRepository


class RecipeService:
    """Orchestrates recipe-catalog use cases over the repository port."""

    def __init__(self, recipe_repository: RecipeRepository) -> None:
        self._recipes = recipe_repository

    def get_recipe(self, recipe_id: str) -> Recipe:
        """Return the full catalog recipe with *recipe_id*, or raise (DPL-203).

        The catalog is shared (not owner-scoped), so a miss is an unambiguous "not found": the
        repository read is keyed by id alone and an absent id raises
        :class:`~app.domain.errors.RecipeDetailNotFoundError` (mapped to ``404``).
        """
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            raise RecipeDetailNotFoundError(recipe_id)
        return recipe

    def search_recipes(self, query: SearchRecipesQuery) -> list[Recipe]:
        """Return recipes matching the filters with ingredient relevance + stable paging.

        Implements DPL-202 (filters/pagination) with DPL-206 ingredient relevance.

        An empty/over-broad query is handled gracefully: with no filters every recipe is eligible,
        bounded by ``limit`` and ordered deterministically by the repository so paging is stable.
        When ``ingredients`` are supplied the repository ranks by ingredient overlap (DPL-206).
        """
        skip = (query.page - 1) * query.limit
        return self._recipes.search(
            ingredients=list(query.ingredients) or None,
            diet_type=query.diet_type,
            max_calories=query.max_calories,
            min_protein=query.min_protein,
            skip=skip,
            limit=query.limit,
        )
