"""Nutrition-bounds enforcement: clamp targets, reject physically-impossible recipes (AIA-502).

"AI suggestions stay within sane nutritional bounds." Two enforcement points implement that:

* **Clamp the request targets.** The transport edge already rejects an out-of-range
  ``dailyCalorieTarget`` (AIA-201 schema), but the use case does not trust its caller -- it clamps
  the daily target into ``[1200, 5000]`` and caps the otherwise-unbounded per-meal target at the
  daily ceiling, so the prompt and the AIA-204 alignment always work from a sane number.
* **Reject the model's output.** Nothing upstream can validate what the LLM returns, so each
  recommended recipe is screened for physical sanity -- positive, not-absurd calories; non-negative
  macros; sugar within carbs; and macros that actually add up to the stated calories (4/4/9 kcal per
  gram, within a generous tolerance). A recipe that fails is dropped before the user ever sees it.

Both actions are recorded through a :class:`BoundsTelemetry` port so clamps and rejections are
logged and counted. Rejection is surgical (only the offending recipe is removed, mirroring the
AIA-501 allergen filter); if every suggestion is rejected the recommendation degrades to the empty
fallback the service already returns for unusable model output. Everything here is pure (no LLM or
I/O), so it is fully unit-testable and reproducible, and it backs the AIA-506 adversarial suite.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.recommendations.commands import RecommendationCommand
from app.recommendations.recipes import RecommendedNutrition, RecommendedRecipe

_LOGGER = logging.getLogger("app.recommendations.bounds")

MIN_DAILY_CALORIES = 1200
MAX_DAILY_CALORIES = 5000

# Macro/calorie consistency tolerance: a recipe is only rejected when the energy implied by its
# macros (4 kcal/g protein and carbs, 9 kcal/g fat) misses the stated calories by more than the
# larger of these -- generous enough that ordinary model rounding passes, strict enough to catch
# numbers that cannot be real.
_MISMATCH_ABS_KCAL = 150
_MISMATCH_REL = 0.30
# Sugar is a subset of carbohydrate; allow a couple of grams of rounding slack before flagging.
_SUGAR_GRACE_GRAMS = 2

_PROTEIN_KCAL_PER_GRAM = 4
_CARB_KCAL_PER_GRAM = 4
_FAT_KCAL_PER_GRAM = 9


class BoundsReason(StrEnum):
    """Why a recipe was rejected as nutritionally insane."""

    NON_POSITIVE_CALORIES = "non_positive_calories"
    EXCESSIVE_CALORIES = "excessive_calories"
    NEGATIVE_MACRO = "negative_macro"
    SUGAR_EXCEEDS_CARBS = "sugar_exceeds_carbs"
    MACRO_CALORIE_MISMATCH = "macro_calorie_mismatch"


@dataclass(frozen=True, slots=True)
class CalorieClamp:
    """A target that was pulled back into bounds."""

    field: str
    original: int
    clamped: int


@dataclass(frozen=True, slots=True)
class BoundsViolation:
    """A single (recipe, reason) the bounds guard rejected -- the unit the telemetry counts."""

    recipe_id: str
    recipe_name: str
    reason: BoundsReason


@runtime_checkable
class BoundsTelemetry(Protocol):
    """A write port: record that a target was clamped or a recipe was rejected."""

    def record_clamp(self, clamp: CalorieClamp) -> None: ...

    def record_rejection(self, violation: BoundsViolation) -> None: ...


class InMemoryBoundsTelemetry:
    """Collects clamps and rejections so tests can assert what was enforced and counted."""

    def __init__(self) -> None:
        self.clamps: list[CalorieClamp] = []
        self.rejections: list[BoundsViolation] = []

    def record_clamp(self, clamp: CalorieClamp) -> None:
        self.clamps.append(clamp)

    def record_rejection(self, violation: BoundsViolation) -> None:
        self.rejections.append(violation)

    @property
    def clamp_count(self) -> int:
        """How many targets were clamped."""
        return len(self.clamps)

    @property
    def rejection_count(self) -> int:
        """How many recipe rejections were recorded."""
        return len(self.rejections)


class LoggingBoundsTelemetry:
    """Logs clamps at INFO and rejections at WARNING -- a rejection is operationally noteworthy."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record_clamp(self, clamp: CalorieClamp) -> None:
        self._logger.info(
            "calorie target clamped: field=%s original=%s clamped=%s",
            clamp.field,
            clamp.original,
            clamp.clamped,
        )

    def record_rejection(self, violation: BoundsViolation) -> None:
        self._logger.warning(
            "recipe rejected (bounds): reason=%s recipe=%s",
            violation.reason.value,
            violation.recipe_id,
        )


def _clamp_daily(value: int) -> int:
    return min(max(value, MIN_DAILY_CALORIES), MAX_DAILY_CALORIES)


def _clamp_meal(value: int) -> int:
    return min(value, MAX_DAILY_CALORIES)


def _rejection_reasons(nutrition: RecommendedNutrition) -> list[BoundsReason]:
    """Every way a recipe's nutrition is physically impossible (empty list means it is sane)."""
    reasons: list[BoundsReason] = []
    calories = nutrition.calories
    if calories <= 0:
        reasons.append(BoundsReason.NON_POSITIVE_CALORIES)
    elif calories > MAX_DAILY_CALORIES:
        reasons.append(BoundsReason.EXCESSIVE_CALORIES)

    macros = (nutrition.protein, nutrition.carbs, nutrition.fat, nutrition.sugar)
    if any(value is not None and value < 0 for value in macros):
        reasons.append(BoundsReason.NEGATIVE_MACRO)

    if (
        nutrition.sugar is not None
        and nutrition.carbs is not None
        and nutrition.sugar > nutrition.carbs + _SUGAR_GRACE_GRAMS
    ):
        reasons.append(BoundsReason.SUGAR_EXCEEDS_CARBS)

    if calories > 0 and None not in (nutrition.protein, nutrition.carbs, nutrition.fat):
        implied = (
            _PROTEIN_KCAL_PER_GRAM * nutrition.protein
            + _CARB_KCAL_PER_GRAM * nutrition.carbs
            + _FAT_KCAL_PER_GRAM * nutrition.fat
        )
        if abs(implied - calories) > max(_MISMATCH_ABS_KCAL, _MISMATCH_REL * calories):
            reasons.append(BoundsReason.MACRO_CALORIE_MISMATCH)

    return reasons


class NutritionBoundsGuard:
    """Clamp a command's calorie targets and reject nutritionally-insane recommended recipes."""

    def __init__(self, telemetry: BoundsTelemetry | None = None) -> None:
        self._telemetry = telemetry or LoggingBoundsTelemetry()

    def clamp(self, command: RecommendationCommand) -> RecommendationCommand:
        """Return the command with its calorie targets pulled into sane bounds (caller-agnostic)."""
        changes: dict[str, int] = {}
        daily = command.daily_calorie_target
        if daily is not None:
            clamped = _clamp_daily(daily)
            if clamped != daily:
                self._telemetry.record_clamp(
                    CalorieClamp(field="daily_calorie_target", original=daily, clamped=clamped)
                )
                changes["daily_calorie_target"] = clamped

        meal = command.calorie_target
        if meal is not None:
            clamped = _clamp_meal(meal)
            if clamped != meal:
                self._telemetry.record_clamp(
                    CalorieClamp(field="calorie_target", original=meal, clamped=clamped)
                )
                changes["calorie_target"] = clamped

        if not changes:
            return command
        return dataclasses.replace(command, **changes)

    def enforce(self, recipes: tuple[RecommendedRecipe, ...]) -> tuple[RecommendedRecipe, ...]:
        """Return only the recipes whose nutrition is sane, recording one rejection per reason."""
        kept: list[RecommendedRecipe] = []
        for recipe in recipes:
            reasons = _rejection_reasons(recipe.nutrition)
            if reasons:
                for reason in reasons:
                    self._telemetry.record_rejection(
                        BoundsViolation(recipe_id=recipe.id, recipe_name=recipe.name, reason=reason)
                    )
            else:
                kept.append(recipe)
        return tuple(kept)
