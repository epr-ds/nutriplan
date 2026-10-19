"""MongoDB adapter for the Favorite repository port (DPL-607)."""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.db.mongo import favorites
from app.domain.favorite import Favorite
from app.domain.repositories import FavoriteRepository


class MongoFavoriteRepository(FavoriteRepository):
    """Stores a user's favorite recipes in MongoDB, always scoped to the owning ``userId``."""

    def __init__(self, collection: Collection | None = None) -> None:
        self._coll = collection if collection is not None else favorites()

    def add(self, favorite: Favorite) -> None:
        doc = favorite.to_document()
        key = {"userId": favorite.user_id, "recipeId": favorite.recipe_id}
        try:
            # An upsert keyed on (userId, recipeId): saving twice keeps the first document (and
            # its createdAt), so the operation is idempotent and the list order does not jump.
            self._coll.update_one(key, {"$setOnInsert": doc}, upsert=True)
        except DuplicateKeyError:
            # Two concurrent first saves raced on the unique index; the other one won, which is
            # exactly the state this call wanted.
            pass

    def remove(self, user_id: str, recipe_id: str) -> None:
        self._coll.delete_one({"userId": user_id, "recipeId": recipe_id})

    def list_for_user(self, user_id: str, *, skip: int = 0, limit: int = 20) -> list[Favorite]:
        cursor = (
            self._coll.find({"userId": user_id})
            .sort([("createdAt", DESCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        return [Favorite.from_document(doc) for doc in cursor]
