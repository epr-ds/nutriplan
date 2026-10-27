"""Recipe data validation + validation report (DPL-205).

While :class:`~app.domain.recipe.Recipe` enforces its invariants at construction time (required
fields, positive servings, non-negative nutrition, canonical units), this module exposes the
pure, dataset-level validation surface used by QA/CI to audit curated recipe rows and to produce a
:class:`RecipeValidationReport` — the "validation report produced for the dataset" of the issue.

The report is deliberately dumb: it walks a collection of recipes and collects one
:class:`RecipeValidationIssue` per rule violation. It never mutates state, so it can be reused over
seed catalogs, imported fixtures or any other recipe source.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.recipe import NUTRIENT_FIELDS, Recipe, normalize_unit


@dataclass(frozen=True)
class RecipeValidationIssue:
    """A single rule violation found while validating a recipe row."""

    recipe_id: str
    field: str
    message: str


@dataclass(frozen=True)
class RecipeValidationReport:
    """Outcome of validating a collection of recipe rows."""

    total: int
    valid: int
    invalid: int
    issues: tuple[RecipeValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        """``True`` when no recipe row was rejected."""
        return self.invalid == 0


def _nutrition_is_sane(nutrition) -> bool:
    if nutrition is None:
        return True
    return all(
        getattr(nutrition, field_name) is None or getattr(nutrition, field_name) >= 0
        for field_name in NUTRIENT_FIELDS
    )


def validate_recipe(recipe: Recipe) -> list[RecipeValidationIssue]:
    """Return every :class:`RecipeValidationIssue` violated by *recipe* (possibly none)."""
    issues: list[RecipeValidationIssue] = []

    if not recipe.name:
        issues.append(RecipeValidationIssue(recipe.id, "name", "missing or blank name"))
    if recipe.servings < 1:
        issues.append(RecipeValidationIssue(recipe.id, "servings", "servings must be >= 1"))

    if recipe.nutritional_info is not None and not _nutrition_is_sane(recipe.nutritional_info):
        issues.append(
            RecipeValidationIssue(recipe.id, "nutritionalInfo", "negative nutrition value")
        )

    for index, ingredient in enumerate(recipe.ingredients):
        if ingredient.quantity is not None and ingredient.quantity < 0:
            issues.append(
                RecipeValidationIssue(
                    recipe.id, f"ingredients[{index}].quantity", "negative quantity"
                )
            )
        if ingredient.unit is not None and normalize_unit(ingredient.unit) != ingredient.unit:
            issues.append(
                RecipeValidationIssue(recipe.id, f"ingredients[{index}].unit", "unit not canonical")
            )

    return issues


def validate_recipes(recipes: Iterable[Recipe]) -> RecipeValidationReport:
    """Validate *recipes* and summarize them into a :class:`RecipeValidationReport`."""
    items = list(recipes)
    issues: list[RecipeValidationIssue] = []
    invalid_count = 0
    for recipe in items:
        recipe_issues = validate_recipe(recipe)
        if recipe_issues:
            invalid_count += 1
        issues.extend(recipe_issues)

    return RecipeValidationReport(
        total=len(items),
        valid=len(items) - invalid_count,
        invalid=invalid_count,
        issues=tuple(issues),
    )
