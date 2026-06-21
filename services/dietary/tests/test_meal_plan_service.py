"""DPL-102 application-layer tests: the create-meal-plan use case (Mongo-free)."""

from datetime import date

import pytest

from app.application.commands import CreateMealPlanCommand, ListMealPlansQuery
from app.application.meal_plan_service import MealPlanService
from app.domain.errors import MealPlanDateRangeError, MealPlanNotFoundError
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


def test_list_meal_plans_returns_only_owner_plans():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)
    service.create_meal_plan(_command(user_id="owner", name="A"))
    service.create_meal_plan(_command(user_id="owner", name="B"))
    service.create_meal_plan(_command(user_id="intruder", name="C"))

    plans = service.list_meal_plans(ListMealPlansQuery(user_id="owner"))

    assert {p.name for p in plans} == {"A", "B"}


def test_list_meal_plans_translates_page_to_skip():
    class _SpyRepo(InMemoryMealPlanRepository):
        def __init__(self) -> None:
            super().__init__()
            self.last_call: dict | None = None

        def list_for_user(self, user_id, *, status=None, skip=0, limit=20):
            self.last_call = {"user_id": user_id, "status": status, "skip": skip, "limit": limit}
            return super().list_for_user(user_id, status=status, skip=skip, limit=limit)

    repo = _SpyRepo()
    service = MealPlanService(repo)

    service.list_meal_plans(ListMealPlansQuery(user_id="u", page=3, limit=10))

    assert repo.last_call == {"user_id": "u", "status": None, "skip": 20, "limit": 10}


def test_list_meal_plans_passes_status_filter_to_repository():
    class _SpyRepo(InMemoryMealPlanRepository):
        def __init__(self) -> None:
            super().__init__()
            self.last_status: object = "unset"

        def list_for_user(self, user_id, *, status=None, skip=0, limit=20):
            self.last_status = status
            return []

    repo = _SpyRepo()
    service = MealPlanService(repo)

    service.list_meal_plans(ListMealPlansQuery(user_id="u", status=MealPlanStatus.ACTIVE))

    assert repo.last_status == MealPlanStatus.ACTIVE


def test_get_meal_plan_returns_owned_plan():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)
    created = service.create_meal_plan(_command(user_id="owner"))

    fetched = service.get_meal_plan("owner", created.id)

    assert fetched.id == created.id
    assert fetched.user_id == "owner"


def test_get_meal_plan_raises_not_found_when_missing():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)

    with pytest.raises(MealPlanNotFoundError):
        service.get_meal_plan("owner", "does-not-exist")


def test_get_meal_plan_raises_not_found_for_other_users_plan():
    repo = InMemoryMealPlanRepository()
    service = MealPlanService(repo)
    created = service.create_meal_plan(_command(user_id="owner"))

    with pytest.raises(MealPlanNotFoundError):
        service.get_meal_plan("intruder", created.id)
