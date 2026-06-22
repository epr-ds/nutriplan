"""Recipe aggregate (DPL-201).

A ``Recipe`` is the second aggregate root of the Dietary Planning bounded context. It **owns** its
embedded :class:`Ingredient` value objects and carries a per-serving :class:`NutritionalInfo`, all
persisted as a single ``recipes`` document. Recipes form a shared catalog — unlike meal plans they
are not owner-scoped — and are referenced from a :class:`~app.domain.meal_plan.PlannedMeal` by id
only, so the two aggregates never cross each other's consistency boundary.
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


class _Model(BaseModel):
    """Base for recipe models: camelCase wire/document keys, lenient on read."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )


class NutritionalInfo(_Model):
    """Macro/energy breakdown. On a recipe this is expressed **per serving** (DPL-201)."""

    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class Ingredient(_Model):
    """A single ingredient line within a :class:`Recipe`.

    Part of the Recipe aggregate: ingredients have no independent lifecycle and are only ever
    created or mutated through their owning recipe.
    """

    name: str = Field(min_length=1)
    quantity: float | None = None
    unit: str | None = None
    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class Recipe(_Model):
    """Aggregate root: a catalog recipe with its ingredients and per-serving nutrition."""

    id: str = Field(default_factory=_new_id)
    name: str = Field(min_length=1)
    description: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    prep_time: int | None = None
    cook_time: int | None = None
    servings: int = Field(gt=0)
    image_url: str | None = None
    nutritional_info: NutritionalInfo | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        servings: int,
        description: str | None = None,
        ingredients: list[Ingredient] | None = None,
        instructions: list[str] | None = None,
        prep_time: int | None = None,
        cook_time: int | None = None,
        image_url: str | None = None,
        nutritional_info: NutritionalInfo | None = None,
    ) -> Recipe:
        """Create a new recipe, enforcing the aggregate's invariants.

        ``servings`` must be positive (per-serving nutrition is only meaningful for at least one
        serving) and ``name`` must be non-empty; both are enforced by the model's field
        constraints, which raise a :class:`ValueError` on violation.
        """
        return cls(
            name=name,
            servings=servings,
            description=description,
            ingredients=ingredients or [],
            instructions=instructions or [],
            prep_time=prep_time,
            cook_time=cook_time,
            image_url=image_url,
            nutritional_info=nutritional_info,
        )

    def to_document(self) -> dict:
        """Serialize to a MongoDB document: camelCase keys, aggregate id stored as ``_id``."""
        doc = self.model_dump(by_alias=True, mode="json", exclude_none=True)
        doc["_id"] = doc.pop("id")
        return doc

    @classmethod
    def from_document(cls, doc: dict) -> Recipe:
        """Rehydrate an aggregate from its MongoDB document."""
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls.model_validate(data)
