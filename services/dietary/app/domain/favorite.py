"""Favorite recipes (DPL-607): the recipes a user has saved to find again.

A favorite is a small per-user link to a catalog recipe, not a copy of it: the recipe stays the one
shared document, so favoriting never goes stale when the catalog is corrected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Favorite(BaseModel):
    """One user's saved recipe. Unique per ``(user_id, recipe_id)``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = Field(default_factory=_new_id)
    user_id: str
    recipe_id: str
    created_at: datetime = Field(default_factory=_utcnow)

    def to_document(self) -> dict:
        """Serialize to a MongoDB document: camelCase keys, aggregate id stored as ``_id``."""
        doc = self.model_dump(by_alias=True, mode="json")
        doc["_id"] = doc.pop("id")
        return doc

    @classmethod
    def from_document(cls, doc: dict) -> Favorite:
        """Rehydrate a favorite from its MongoDB document."""
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls.model_validate(data)
