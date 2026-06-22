"""Reusable test doubles for the Dietary service."""

from __future__ import annotations

from app.domain.dietary_types import DietaryType
from app.domain.meal_plan import MealPlan, MealPlanStatus
from app.domain.recipe import Recipe
from app.domain.repositories import MealPlanRepository, RecipeRepository


class InMemoryMealPlanRepository(MealPlanRepository):
    """A dict-backed :class:`MealPlanRepository` for fast, Mongo-free unit tests."""

    def __init__(self) -> None:
        self.saved: dict[str, MealPlan] = {}

    def add(self, plan: MealPlan) -> None:
        self.saved[plan.id] = plan

    def get(self, user_id: str, plan_id: str) -> MealPlan | None:
        plan = self.saved.get(plan_id)
        return plan if plan is not None and plan.user_id == user_id else None

    def update(self, plan: MealPlan) -> None:
        existing = self.saved.get(plan.id)
        if existing is not None and existing.user_id == plan.user_id:
            self.saved[plan.id] = plan

    def list_for_user(
        self,
        user_id: str,
        *,
        status: MealPlanStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MealPlan]:
        plans = [p for p in self.saved.values() if p.user_id == user_id]
        if status is not None:
            want = status.value if isinstance(status, MealPlanStatus) else status
            plans = [p for p in plans if p.status == want]
        # Newest first, with a stable id tiebreaker — mirrors the Mongo adapter's ordering.
        plans.sort(key=lambda p: (p.created_at, p.id), reverse=True)
        return plans[skip : skip + limit]


class InMemoryRecipeRepository(RecipeRepository):
    """A dict-backed :class:`RecipeRepository` for fast, Mongo-free unit tests."""

    def __init__(self) -> None:
        self.saved: dict[str, Recipe] = {}

    def add(self, recipe: Recipe) -> None:
        self.saved[recipe.id] = recipe

    def get(self, recipe_id: str) -> Recipe | None:
        return self.saved.get(recipe_id)

    def search(
        self,
        *,
        ingredients: list[str] | None = None,
        diet_type: DietaryType | None = None,
        max_calories: int | None = None,
        min_protein: float | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Recipe]:
        results = list(self.saved.values())
        if ingredients:
            wanted = [name.strip().lower() for name in ingredients if name and name.strip()]
            if wanted:
                results = [
                    r for r in results if {i.name.lower() for i in r.ingredients}.issuperset(wanted)
                ]
        if diet_type is not None:
            dt = diet_type.value if isinstance(diet_type, DietaryType) else diet_type
            results = [r for r in results if dt in r.dietary_types]
        if max_calories is not None:
            results = [
                r for r in results if _calories(r) is not None and _calories(r) <= max_calories
            ]
        if min_protein is not None:
            results = [r for r in results if _protein(r) is not None and _protein(r) >= min_protein]
        # Deterministic (name, id) ordering mirrors the Mongo adapter, so paging is stable.
        results.sort(key=lambda r: (r.name, r.id))
        return results[skip : skip + limit]


def _calories(recipe: Recipe) -> int | None:
    return recipe.nutritional_info.calories if recipe.nutritional_info is not None else None


def _protein(recipe: Recipe) -> float | None:
    return recipe.nutritional_info.protein if recipe.nutritional_info is not None else None
