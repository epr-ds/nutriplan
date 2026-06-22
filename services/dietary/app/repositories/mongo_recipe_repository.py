"""MongoDB adapter for the Recipe repository port (DPL-201/202)."""

from __future__ import annotations

import re

from pymongo import ASCENDING
from pymongo.collection import Collection

from app.db.mongo import recipes
from app.domain.dietary_types import DietaryType
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

    def search(
        self,
        *,
        ingredients: list[str] | None = None,
        diet_type: DietaryType | None = None,
        max_calories: int | None = None,
        min_protein: float | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Recipe]:
        """Translate the filters into a single Mongo query and page deterministically (DPL-202).

        Each filter that is set narrows the query (AND). Ingredient matching uses anchored,
        case-insensitive regexes via ``$all`` so the recipe must contain every requested name; the
        macro bounds and diet membership use the indexes installed by ``ensure_recipes_collection``.
        """
        query: dict = {}
        if ingredients:
            patterns = [
                re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)
                for name in ingredients
                if name and name.strip()
            ]
            if patterns:
                query["ingredients.name"] = {"$all": patterns}
        if diet_type is not None:
            query["dietaryTypes"] = (
                diet_type.value if isinstance(diet_type, DietaryType) else diet_type
            )
        if max_calories is not None:
            query["nutritionalInfo.calories"] = {"$lte": max_calories}
        if min_protein is not None:
            query["nutritionalInfo.protein"] = {"$gte": min_protein}

        cursor = (
            self._coll.find(query)
            .sort([("name", ASCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        return [Recipe.from_document(doc) for doc in cursor]
