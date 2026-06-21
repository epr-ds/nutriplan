"""DPL-102 application-layer tests: the create-meal-plan use case (Mongo-free)."""

from datetime import date

import pytest

from app.application.commands import CreateMealPlanCommand
from app.application.meal_plan_service import MealPlanService
from app.domain.errors import MealPlanDateRangeError
from app.domain.meal_plan import MealPlanStatus
from tests.fakes import InMemoryMealPlanRepository


def _command(**overrides) -> CreateMealPlanCommand:
    defaults = dict(
        user_id="user-1",
        name="Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )
    defaults.update(overrides)
    return CreateMealPlanCommand(**defaults)


def test_create_persists_and_returns_draft_plan():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)

    plan = service.create_meal_plan(_command())

    assert plan.id in repo.saved
    assert plan.status == MealPlanStatus.DRAFT.value
    assert plan.user_id == "user-1"


def test_create_is_scoped_to_command_user():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)

    plan = service.create_meal_plan(_command(user_id="owner"))

    assert repo.get("owner", plan.id) is not None
    assert repo.get("intruder", plan.id) is None


def test_create_propagates_date_range_invariant_and_persists_nothing():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)

    with pytest.raises(MealPlanDateRangeError):
        service.create_meal_plan(_command(start_date=date(2026, 1, 7), end_date=date(2026, 1, 1)))

    assert repo.saved == {}
