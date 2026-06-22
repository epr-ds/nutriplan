"""Per-meal nutrition computation (DPL-301).

A planned meal references a recipe and a number of ``servings``; this pure domain service derives
the meal's :class:`~app.domain.meal_plan.NutritionalInfo` from that recipe, scaled to the meal.

**Source of truth.** A recipe's per-serving nutrition is taken from its authored
``nutritionalInfo`` when present (the curated, official figure). Otherwise it is derived from the
recipe's ingredient breakdown, whose macros record the amounts for the recipe *as written* — i.e.
for ``recipe.servings`` servings — so per serving is ``Sum(ingredients) / recipe.servings``. This
matches the seed catalog, where ``Sum(ingredients) / servings`` equals the stored
``nutritionalInfo``. A meal of ``servings`` servings therefore contributes
``per_serving * servings``.

**Rounding.** All arithmetic is done in exact decimal and rounded once, at the end, **half-up**
(``242.5 -> 243``, ``14.85 -> 14.9``): energy to the nearest whole calorie and each macro gram to a
single decimal place.

**Unknown vs zero.** A nutrient with no data wherever it is read stays ``None`` rather than being
reported as ``0`` — "not measured" is kept distinct from "measured as zero".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.domain.meal_plan import (
    MealPlan,
    NutritionalInfo,
    NutritionalSummary,
    NutritionalTargets,
)
from app.domain.recipe import Recipe

_MACRO_FIELDS = ("protein", "carbs", "fat", "sugar")
_NUTRIENT_FIELDS = ("calories", *_MACRO_FIELDS)
_CALORIE_QUANTUM = Decimal("1")
_MACRO_QUANTUM = Decimal("0.1")


def compute_meal_nutrition(recipe: Recipe, servings: float) -> NutritionalInfo:
    """Return the nutrition contributed by *servings* servings of *recipe* (DPL-301)."""
    factor = Decimal(str(servings))
    per_serving = _per_serving(recipe)

    def scaled(field: str, quantum: Decimal) -> Decimal | None:
        value = per_serving[field]
        return None if value is None else _round_half_up(value * factor, quantum)

    calories = scaled("calories", _CALORIE_QUANTUM)
    return NutritionalInfo(
        calories=int(calories) if calories is not None else None,
        protein=_as_float(scaled("protein", _MACRO_QUANTUM)),
        carbs=_as_float(scaled("carbs", _MACRO_QUANTUM)),
        fat=_as_float(scaled("fat", _MACRO_QUANTUM)),
        sugar=_as_float(scaled("sugar", _MACRO_QUANTUM)),
    )


def _per_serving(recipe: Recipe) -> dict[str, Decimal | None]:
    """The recipe's per-serving nutrition as exact decimals (``None`` where unknown)."""
    info = recipe.nutritional_info
    if info is not None:
        return {field: _to_decimal(getattr(info, field)) for field in _NUTRIENT_FIELDS}

    servings = Decimal(recipe.servings)  # the Recipe aggregate enforces servings > 0
    per_serving: dict[str, Decimal | None] = {}
    for field in _NUTRIENT_FIELDS:
        knowns = [
            value
            for ingredient in recipe.ingredients
            if (value := _to_decimal(getattr(ingredient, field))) is not None
        ]
        per_serving[field] = sum(knowns, Decimal(0)) / servings if knowns else None
    return per_serving


def _to_decimal(value: float | int | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _round_half_up(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _as_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def summarize_plan_nutrition(plan: MealPlan) -> NutritionalSummary:
    """Summarize *plan*'s overall nutrition versus its targets (DPL-302).

    Rolls every planned meal's nutrition (DPL-301) up into a ``total``, divides that by the plan's
    **inclusive** date span (``start_date``..``end_date``) for the ``daily_average``, and surfaces
    the plan's ``targets``. A nutrient that no meal reports stays ``None`` (unknown != zero). The
    same half-up rule as per-meal nutrition applies (energy to a whole calorie, macros to one
    decimal place). Being derived from the aggregate's current meals, it always reflects the latest
    meals (DPL-105/107).
    """
    totals = _sum_meal_nutrients(plan)
    days = (plan.end_date - plan.start_date).days + 1
    daily = {
        field: (None if value is None else value / Decimal(days)) for field, value in totals.items()
    }
    return NutritionalSummary(
        total=_as_info(totals),
        daily_average=_as_info(daily),
        targets=_plan_targets(plan),
    )


def _sum_meal_nutrients(plan: MealPlan) -> dict[str, Decimal | None]:
    """Exact-decimal sum of each nutrient across the plan's meals (``None`` where unreported)."""
    infos = [meal.nutritional_info for meal in plan.meals if meal.nutritional_info is not None]
    totals: dict[str, Decimal | None] = {}
    for field in _NUTRIENT_FIELDS:
        knowns = [
            value for info in infos if (value := _to_decimal(getattr(info, field))) is not None
        ]
        totals[field] = sum(knowns, Decimal(0)) if knowns else None
    return totals


def _as_info(values: dict[str, Decimal | None]) -> NutritionalInfo:
    """Round exact-decimal nutrients into a ``NutritionalInfo`` (calories whole, macros 1dp)."""
    calories = values["calories"]
    return NutritionalInfo(
        calories=None if calories is None else int(_round_half_up(calories, _CALORIE_QUANTUM)),
        protein=_as_float(_round_macro(values["protein"])),
        carbs=_as_float(_round_macro(values["carbs"])),
        fat=_as_float(_round_macro(values["fat"])),
        sugar=_as_float(_round_macro(values["sugar"])),
    )


def _round_macro(value: Decimal | None) -> Decimal | None:
    return None if value is None else _round_half_up(value, _MACRO_QUANTUM)


def _plan_targets(plan: MealPlan) -> NutritionalTargets:
    """The plan's nutrition goals: daily calorie target plus optional macro gram targets."""
    macros = plan.macro_targets
    return NutritionalTargets(
        calories=plan.daily_calorie_target,
        protein=macros.protein_grams if macros is not None else None,
        carbs=macros.carbs_grams if macros is not None else None,
        fat=macros.fat_grams if macros is not None else None,
        sugar=macros.sugar_grams if macros is not None else None,
    )
