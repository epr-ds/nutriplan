"""MealPlan aggregate (DPL-101).

The Dietary Planning bounded context is organised around a single aggregate root, ``MealPlan``,
which **owns** its embedded ``PlannedMeal`` items. A meal plan and all of its planned meals form
one consistency/transaction boundary and are persisted as a single ``meal_plans`` document — a
planned meal has no independent lifecycle and is never queried or stored on its own. References
that cross aggregate boundaries (the owning user, recipes) are held by **id only**.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class MealPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    SAVED = "saved"


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class DietaryType(StrEnum):
    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    KETO = "keto"
    PALEO = "paleo"


class _Model(BaseModel):
    """Base for aggregate models: camelCase wire/document keys, lenient on read."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )


class MacroTargets(_Model):
    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    sugar_grams: int | None = None


class NutritionalInfo(_Model):
    calories: int | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class PlannedMeal(_Model):
    """A meal planned within a :class:`MealPlan`.

    Part of the MealPlan aggregate: created, mutated, and removed only through its owning plan.
    """

    id: str = Field(default_factory=_new_id)
    meal_type: MealType
    recipe_id: str
    servings: float
    day_index: int | None = None
    nutritional_info: NutritionalInfo | None = None


class MealPlan(_Model):
    """Aggregate root: a user's meal plan with its embedded planned meals."""

    id: str = Field(default_factory=_new_id)
    user_id: str
    name: str = Field(min_length=1)
    start_date: date
    end_date: date
    daily_calorie_target: int
    macro_targets: MacroTargets | None = None
    dietary_type: DietaryType | None = None
    status: MealPlanStatus = MealPlanStatus.DRAFT
    meals: list[PlannedMeal] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_document(self) -> dict:
        """Serialize to a MongoDB document: camelCase keys, aggregate id stored as ``_id``."""
        doc = self.model_dump(by_alias=True, mode="json", exclude_none=True)
        doc["_id"] = doc.pop("id")
        return doc

    @classmethod
    def from_document(cls, doc: dict) -> MealPlan:
        """Rehydrate an aggregate from its MongoDB document."""
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls.model_validate(data)
