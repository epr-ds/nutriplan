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
        """Filter, relevance-rank, and page recipes in a single aggregation (DPL-202/206).

        Diet membership and the macro bounds narrow the result set (AND) and use the indexes
        installed by ``ensure_recipes_collection``. When ``ingredients`` is supplied a recipe is
        eligible if it contains **any** of the requested names (case-insensitive, anchored), and
        results are ranked by **ingredient overlap** — how many of the requested names it contains —
        descending, then by ``name``/``_id`` for stable paging. Pagination is applied after ranking
        so page boundaries respect the relevance order.
        """
        query: dict = {}
        if diet_type is not None:
            query["dietaryTypes"] = (
                diet_type.value if isinstance(diet_type, DietaryType) else diet_type
            )
        if max_calories is not None:
            query["nutritionalInfo.calories"] = {"$lte": max_calories}
        if min_protein is not None:
            query["nutritionalInfo.protein"] = {"$gte": min_protein}

        wanted = (
            [name.strip().lower() for name in ingredients if name and name.strip()]
            if ingredients
            else []
        )

        pipeline: list[dict] = []
        if wanted:
            patterns = [re.compile(f"^{re.escape(name)}$", re.IGNORECASE) for name in wanted]
            # OR-match any requested ingredient, still index-assisted via the multikey index.
            query["ingredients.name"] = {"$in": patterns}
        if query:
            pipeline.append({"$match": query})

        if wanted:
            # Rank by the number of distinct requested ingredients the recipe contains.
            pipeline.append(
                {
                    "$addFields": {
                        "_overlap": {
                            "$size": {
                                "$setIntersection": [
                                    {
                                        "$map": {
                                            "input": "$ingredients",
                                            "as": "i",
                                            "in": {"$toLower": "$$i.name"},
                                        }
                                    },
                                    wanted,
                                ]
                            }
                        }
                    }
                }
            )
            pipeline.append({"$sort": {"_overlap": -1, "name": ASCENDING, "_id": ASCENDING}})
        else:
            pipeline.append({"$sort": {"name": ASCENDING, "_id": ASCENDING}})

        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})
        return [Recipe.from_document(doc) for doc in self._coll.aggregate(pipeline)]
