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

from app.domain.meal_plan import NutritionalInfo
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
