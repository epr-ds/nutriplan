"""Application service for meals embedded in a plan (DPL-105).

Adding a meal is a meal-plan use case that additionally references a **recipe** in the shared
catalog, so unlike :class:`~app.application.meal_plan_service.MealPlanService` (which only needs
the plan repository) this service depends on **both** the meal-plan and recipe repository ports
(constructor injection). Keeping it separate avoids widening the plan-lifecycle service with a
recipe dependency it does not otherwise need.
"""

from __future__ import annotations

from app.application.commands import (
    AddMealToPlanCommand,
    RemoveMealFromPlanCommand,
    UpdateMealInPlanCommand,
)
from app.domain.errors import MealNotFoundError, MealPlanNotFoundError, RecipeNotFoundError
from app.domain.meal_plan import PlannedMeal
from app.domain.nutrition import compute_meal_nutrition
from app.domain.recipe import Recipe
from app.domain.repositories import MealPlanRepository, RecipeRepository


class MealService:
    """Orchestrates adding meals to a plan, validating the referenced recipe exists."""

    def __init__(
        self,
        meal_plan_repository: MealPlanRepository,
        recipe_repository: RecipeRepository,
    ) -> None:
        self._plans = meal_plan_repository
        self._recipes = recipe_repository

    def add_meal_to_plan(self, command: AddMealToPlanCommand) -> tuple[PlannedMeal, Recipe]:
        """Add a meal to the caller's plan and return the new meal with its recipe (DPL-105).

        The plan is loaded owner-scoped — a missing or not-owned plan raises
        :class:`~app.domain.errors.MealPlanNotFoundError` (``404``). An unknown ``recipe_id`` raises
        :class:`~app.domain.errors.RecipeNotFoundError` (``422``), and a non-positive ``servings``
        raises :class:`~app.domain.errors.InvalidServingsError` (``422``) from the aggregate. The
        meal's nutrition is computed from the recipe scaled to ``servings`` (DPL-301) and embedded
        on the planned meal. The mutated plan is persisted only on success.
        """
        plan = self._plans.get(command.user_id, command.plan_id)
        if plan is None:
            raise MealPlanNotFoundError(command.plan_id)
        recipe = self._recipes.get(command.recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(command.recipe_id)
        meal = plan.add_meal(
            meal_type=command.meal_type,
            recipe_id=command.recipe_id,
            servings=command.servings,
            nutritional_info=compute_meal_nutrition(recipe, command.servings),
        )
        self._plans.update(plan)
        return meal, recipe

    def update_meal(self, command: UpdateMealInPlanCommand) -> tuple[PlannedMeal, Recipe | None]:
        """Edit a planned meal's ``servings``, ``day_index`` and/or ``satisfactionLevel`` (DPL-107).

        The plan is loaded owner-scoped (a missing/!owned plan raises
        :class:`~app.domain.errors.MealPlanNotFoundError`, ``404``) and the meal located within it
        (an unknown meal id raises :class:`~app.domain.errors.MealNotFoundError`, ``404``). When
        ``servings`` changes the meal's nutrition is recomputed from its recipe (DPL-301); a missing
        recipe — the catalog changed under the plan — is a ``422``. ``satisfactionLevel`` is the
        1–5 post-meal rating (DPL-304), validated by the aggregate. The mutated plan is persisted
        only on success, and the plan's nutritional summary reflects the edit on the next read.
        """
        plan = self._plans.get(command.user_id, command.plan_id)
        if plan is None:
            raise MealPlanNotFoundError(command.plan_id)
        meal = plan.find_meal(command.meal_id)
        if meal is None:
            raise MealNotFoundError(command.meal_id)

        recipe: Recipe | None = None
        nutritional_info = None
        if command.servings is not None:
            recipe = self._recipes.get(meal.recipe_id)
            if recipe is None:
                raise RecipeNotFoundError(meal.recipe_id)
            nutritional_info = compute_meal_nutrition(recipe, command.servings)

        updated = plan.update_meal(
            command.meal_id,
            servings=command.servings,
            day_index=command.day_index,
            satisfaction_level=command.satisfaction_level,
            nutritional_info=nutritional_info,
        )
        self._plans.update(plan)
        return updated, recipe

    def remove_meal(self, command: RemoveMealFromPlanCommand) -> None:
        """Remove a planned meal from the caller's plan (DPL-107).

        The plan is loaded owner-scoped (missing/!owned → :class:`MealPlanNotFoundError`, ``404``)
        and the meal removed (unknown meal id → :class:`MealNotFoundError`, ``404``). The mutation
        is persisted only on success.
        """
        plan = self._plans.get(command.user_id, command.plan_id)
        if plan is None:
            raise MealPlanNotFoundError(command.plan_id)
        plan.remove_meal(command.meal_id)
        self._plans.update(plan)
