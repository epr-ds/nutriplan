"""Application service (use cases) for meal plans."""

from __future__ import annotations

from app.application.commands import (
    ChangeMealPlanStatusCommand,
    CreateMealPlanCommand,
    ListMealPlansQuery,
)
from app.domain.errors import MealPlanNotFoundError
from app.domain.meal_plan import MealPlan
from app.domain.repositories import MealPlanRepository


class MealPlanService:
    """Orchestrates meal-plan use cases over the domain model and repository port.

    The repository is injected (constructor injection), so the service is agnostic of MongoDB and
    can be unit-tested against an in-memory double.
    """

    def __init__(self, repository: MealPlanRepository) -> None:
        self._repository = repository

    def create_meal_plan(self, command: CreateMealPlanCommand) -> MealPlan:
        """Create and persist a new draft meal plan for the commanding user (DPL-102).

        Invariants (e.g. ``endDate >= startDate``) are enforced by the aggregate factory; a
        violation raises a :class:`~app.domain.errors.DomainError` and nothing is persisted.
        """
        plan = MealPlan.create(
            user_id=command.user_id,
            name=command.name,
            start_date=command.start_date,
            end_date=command.end_date,
            daily_calorie_target=command.daily_calorie_target,
            macro_targets=command.macro_targets,
            dietary_type=command.dietary_type,
        )
        self._repository.add(plan)
        return plan

    def list_meal_plans(self, query: ListMealPlansQuery) -> list[MealPlan]:
        """Return the caller's meal plans, optionally filtered by status, with pagination (DPL-103).

        The 1-based ``page`` is translated to a repository ``skip`` offset; results are scoped to
        ``query.user_id`` by the repository, so a caller can only ever browse their own plans.
        """
        skip = (query.page - 1) * query.limit
        return self._repository.list_for_user(
            query.user_id,
            status=query.status,
            skip=skip,
            limit=query.limit,
        )

    def get_meal_plan(self, user_id: str, plan_id: str) -> MealPlan:
        """Return the caller's plan by id, or raise :class:`MealPlanNotFoundError` (DPL-104).

        The repository read is owner-scoped, so a plan owned by another user surfaces as not found —
        the caller can never distinguish "does not exist" from "exists but isn't yours".
        """
        plan = self._repository.get(user_id, plan_id)
        if plan is None:
            raise MealPlanNotFoundError(plan_id)
        return plan

    def change_meal_plan_status(self, command: ChangeMealPlanStatusCommand) -> MealPlan:
        """Transition one of the caller's plans to a new lifecycle status (DPL-106).

        The plan is loaded owner-scoped (a missing/!owned plan raises
        :class:`~app.domain.errors.MealPlanNotFoundError`), the aggregate enforces the state machine
        (illegal moves / empty-plan activation raise :class:`~app.domain.errors.DomainError`
        subclasses), and only on success is the mutated aggregate persisted.
        """
        plan = self._repository.get(command.user_id, command.plan_id)
        if plan is None:
            raise MealPlanNotFoundError(command.plan_id)
        plan.transition_to(command.target_status)
        self._repository.update(plan)
        return plan
