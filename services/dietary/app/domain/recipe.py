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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.domain.dietary_types import DietaryType

# Canonical nutrition units and their accepted aliases (DPL-205: units are normalized, not trusted).
UNIT_ALIASES: dict[str, str] = {
    # Mass
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "mg": "mg",
    "milligram": "mg",
    "microgram": "ug",
    "micrograms": "ug",
    "ug": "ug",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    # Volume
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "cl": "cl",
    "centiliter": "cl",
    "centiliters": "cl",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "floz": "floz",
    "fluidounce": "floz",
    "fluidounces": "floz",
}

NUTRIENT_FIELDS: tuple[str, ...] = ("calories", "protein", "carbs", "fat", "sugar")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def normalize_unit(unit: str | None) -> str | None:
    """Canonicalize a nutrition unit, accepting common aliases (DPL-205).

    ``None``/blank input stays ``None`` (a nutrient may simply not be measured); recognised
    variants — ``"Grams"``, ``"grams"``, ``"g"`` … — collapse to one canonical symbol. An
    unrecognised unit is rejected with a :class:`ValueError` so bad catalog rows fail loudly
    instead of flowing into nutrition math.
    """
    if unit is None:
        return None
    canonical = UNIT_ALIASES.get(unit.strip().lower())
    if canonical is None:
        raise ValueError(f"unknown nutrition unit: {unit!r}")
    return canonical


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

    @model_validator(mode="after")
    def _validate_bounds(self) -> NutritionalInfo:
        """Reject negative nutrition figures (DPL-205): a nutrient can be unknown, never harmful."""
        for field_name in NUTRIENT_FIELDS:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be a non-negative amount, got {value}")
        return self


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

    @field_validator("unit", mode="before")
    @classmethod
    def _normalize_unit(cls, value: object) -> object:
        """Canonicalize the unit on intake (``"Grams"`` -> ``"g"``); blank stays ``None``."""
        if value is None:
            return None
        return normalize_unit(str(value))

    @model_validator(mode="after")
    def _validate_bounds(self) -> Ingredient:
        """Enforce DPL-205 bounds: no negative quantities or nutrition figures."""
        if self.quantity is not None and self.quantity < 0:
            raise ValueError(f"quantity must be a non-negative amount, got {self.quantity}")
        for field_name in NUTRIENT_FIELDS:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be a non-negative amount, got {value}")
        return self


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
    dietary_types: list[DietaryType] = Field(default_factory=list)
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
        dietary_types: list[DietaryType] | None = None,
    ) -> Recipe:
        """Create a new recipe, enforcing the aggregate's invariants.

        ``servings`` must be positive (per-serving nutrition is only meaningful for at least one
        serving) and ``name`` must be non-empty; both are enforced by the model's field
        constraints, which raise a :class:`ValueError` on violation. ``dietary_types`` declares the
        diets the recipe is compatible with (used by recipe search, DPL-202).
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
            dietary_types=dietary_types or [],
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
