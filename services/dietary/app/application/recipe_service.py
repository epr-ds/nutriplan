"""Application service (use cases) for the recipe catalog (DPL-202).

The catalog is a global, read-mostly resource (not owner-scoped), so this service is a thin use-case
layer over the :class:`~app.domain.repositories.RecipeRepository` port: it translates the
``SearchRecipesQuery`` DTO (notably 1-based ``page`` -> ``skip`` offset) and delegates the actual
filtering + ordering to the repository, which can use its indexes. The repository is injected
(constructor injection) so the service is agnostic of MongoDB and unit-testable against a double.
"""

from __future__ import annotations

from app.application.commands import SearchRecipesQuery
from app.domain.recipe import Recipe
from app.domain.repositories import RecipeRepository


class RecipeService:
    """Orchestrates recipe-catalog use cases over the repository port."""

    def __init__(self, recipe_repository: RecipeRepository) -> None:
        self._recipes = recipe_repository

    def search_recipes(self, query: SearchRecipesQuery) -> list[Recipe]:
        """Return recipes matching the supplied filters with stable offset pagination (DPL-202).

        An empty/over-broad query is handled gracefully: with no filters every recipe is eligible,
        bounded by ``limit`` and ordered deterministically by the repository so paging is stable.
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
