"""MongoDB adapter for the Recipe repository port (DPL-201)."""

from __future__ import annotations

from pymongo.collection import Collection

from app.db.mongo import recipes
from app.domain.recipe import Recipe
from app.domain.repositories import RecipeRepository


class MongoRecipeRepository(RecipeRepository):
    """Stores and retrieves :class:`Recipe` aggregates in MongoDB (shared catalog, not scoped)."""

    def __init__(self, collection: Collection | None = None) -> None:
        self._coll = collection if collection is not None else recipes()

    def add(self, recipe: Recipe) -> None:
        self._coll.insert_one(recipe.to_document())

    def get(self, recipe_id: str) -> Recipe | None:
        doc = self._coll.find_one({"_id": recipe_id})
        return Recipe.from_document(doc) if doc else None
