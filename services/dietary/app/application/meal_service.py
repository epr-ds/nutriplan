"""Application service for meals embedded in a plan (DPL-105).

Adding a meal is a meal-plan use case that additionally references a **recipe** in the shared
catalog, so unlike :class:`~app.application.meal_plan_service.MealPlanService` (which only needs
the plan repository) this service depends on **both** the meal-plan and recipe repository ports
(constructor injection). Keeping it separate avoids widening the plan-lifecycle service with a
recipe dependency it does not otherwise need.
"""

from __future__ import annotations

from app.application.commands import AddMealToPlanCommand
from app.domain.errors import MealPlanNotFoundError, RecipeNotFoundError
from app.domain.meal_plan import PlannedMeal
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
        mutated plan is persisted only on success.
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
        )
        self._plans.update(plan)
        return meal, recipe
