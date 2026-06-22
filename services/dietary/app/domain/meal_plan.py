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

from app.domain.dietary_types import DietaryType
from app.domain.errors import (
    EmptyMealPlanActivationError,
    IllegalStateTransitionError,
    InvalidServingsError,
    MealPlanDateRangeError,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class MealPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    SAVED = "saved"


# The meal-plan lifecycle as an explicit, data-driven state machine: a plan is drafted, activated
# once it has meals, then either completed or saved (both terminal). Encoding the legal moves here
# (rather than as scattered ``if`` checks) keeps the policy in one auditable place.
_ALLOWED_TRANSITIONS: dict[MealPlanStatus, frozenset[MealPlanStatus]] = {
    MealPlanStatus.DRAFT: frozenset({MealPlanStatus.ACTIVE}),
    MealPlanStatus.ACTIVE: frozenset({MealPlanStatus.COMPLETED, MealPlanStatus.SAVED}),
    MealPlanStatus.COMPLETED: frozenset(),
    MealPlanStatus.SAVED: frozenset(),
}


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


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


class NutritionalTargets(_Model):
    """A plan's nutrition goals: its daily calorie target plus optional macro gram targets.

    A flattened, read-facing view of the plan's ``daily_calorie_target`` and ``macro_targets`` used
    by the nutritional summary (DPL-302); the macros are ``None`` when the plan sets no targets.
    """

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None


class NutritionalSummary(_Model):
    """A plan's overall nutrition versus its targets (DPL-302).

    A *derived* value object (never persisted): the ``total`` nutrition across all of the plan's
    meals, the ``daily_average`` over the plan's date span, and the plan's ``targets``. It is
    recomputed from the aggregate's current meals on every read, so it always reflects the latest
    meals (DPL-105/107).
    """

    total: NutritionalInfo
    daily_average: NutritionalInfo
    targets: NutritionalTargets


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

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        name: str,
        start_date: date,
        end_date: date,
        daily_calorie_target: int,
        macro_targets: MacroTargets | None = None,
        dietary_type: DietaryType | None = None,
    ) -> MealPlan:
        """Create a new draft meal plan for *user_id*, enforcing the aggregate's invariants.

        A plan always starts in :attr:`MealPlanStatus.DRAFT` (DPL-102). The only creation-time
        invariant is that the planning window is non-empty — ``end_date`` must be on or after
        ``start_date`` — otherwise :class:`~app.domain.errors.MealPlanDateRangeError` is raised.
        """
        if end_date < start_date:
            raise MealPlanDateRangeError(start_date, end_date)
        return cls(
            user_id=user_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            daily_calorie_target=daily_calorie_target,
            macro_targets=macro_targets,
            dietary_type=dietary_type,
            status=MealPlanStatus.DRAFT,
        )

    def transition_to(self, target: MealPlanStatus) -> None:
        """Move the plan to *target* status, enforcing the lifecycle state machine.

        Raises :class:`~app.domain.errors.IllegalStateTransitionError` if the move is not allowed
        from the current status, or :class:`~app.domain.errors.EmptyMealPlanActivationError` if the
        (otherwise legal) activation is attempted on a plan with no meals. On success the plan's
        ``updated_at`` is bumped to record the change.
        """
        current = MealPlanStatus(self.status)
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise IllegalStateTransitionError(current, target)
        if target is MealPlanStatus.ACTIVE and not self.meals:
            raise EmptyMealPlanActivationError(self.id)
        self.status = target.value
        self.updated_at = _utcnow()

    def activate(self) -> None:
        """Activate a draft plan (requires at least one meal)."""
        self.transition_to(MealPlanStatus.ACTIVE)

    def complete(self) -> None:
        """Mark an active plan as completed."""
        self.transition_to(MealPlanStatus.COMPLETED)

    def save(self) -> None:
        """Save an active plan (e.g. as a reusable template)."""
        self.transition_to(MealPlanStatus.SAVED)

    def add_meal(
        self,
        *,
        meal_type: MealType,
        recipe_id: str,
        servings: float,
        day_index: int | None = None,
        nutritional_info: NutritionalInfo | None = None,
    ) -> PlannedMeal:
        """Add a planned meal (a recipe reference + servings) to the plan and return it (DPL-105).

        Enforces the only intrinsic invariant of a planned meal -- ``servings`` must be strictly
        positive -- raising :class:`~app.domain.errors.InvalidServingsError` otherwise and leaving
        the plan unchanged. The referenced recipe's *existence* is a cross-aggregate concern handled
        by the application layer, not here. On success ``updated_at`` is bumped.
        """
        if servings <= 0:
            raise InvalidServingsError(servings)
        meal = PlannedMeal(
            meal_type=meal_type,
            recipe_id=recipe_id,
            servings=servings,
            day_index=day_index,
            nutritional_info=nutritional_info,
        )
        self.meals.append(meal)
        self.updated_at = _utcnow()
        return meal

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
