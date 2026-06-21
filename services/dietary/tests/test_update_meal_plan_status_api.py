"""DPL-106 API tests for ``PATCH /meal-plans/{planId}`` (Mongo-free via dependency overrides).

Exercises the real router, auth dependency, owner scoping and the lifecycle state machine surfaced
over HTTP: legal transitions (200, persisted), illegal transitions (409), activating an empty plan
(422), an unknown/!owned plan (404), unauthenticated calls (401) and invalid target values (422).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_plan_service, get_token_verifier
from app.application.meal_plan_service import MealPlanService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import MealPlan, MealPlanStatus, MealType, PlannedMeal
from app.main import app
from tests.fakes import InMemoryMealPlanRepository

GOOD_TOKEN = "good-token"


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


@pytest.fixture
def repo() -> InMemoryMealPlanRepository:
    return InMemoryMealPlanRepository()


@pytest.fixture
def principal() -> Principal:
    return Principal(user_id="user-123", email="a@b.com")


@pytest.fixture
def client(repo, principal):
    app.dependency_overrides[get_meal_plan_service] = lambda: MealPlanService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(
    repo: InMemoryMealPlanRepository,
    user_id: str,
    *,
    status: MealPlanStatus = MealPlanStatus.DRAFT,
    with_meal: bool = True,
) -> MealPlan:
    plan = MealPlan(
        user_id=user_id,
        name="Cutting",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=status,
        meals=[PlannedMeal(meal_type=MealType.BREAKFAST, recipe_id="r1", servings=1.0)]
        if with_meal
        else [],
    )
    repo.add(plan)
    return plan


def test_patch_requires_authentication(client, repo, principal):
    plan = _seed(repo, principal.user_id)
    assert client.patch(f"/meal-plans/{plan.id}", json={"status": "active"}).status_code == 401


def test_patch_activates_plan_and_persists(client, repo, principal):
    plan = _seed(repo, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=True)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "active"}, headers=_auth())

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    # Reflected in detail (DPL-104) — i.e. the change was persisted.
    assert client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()["status"] == "active"


def test_patch_illegal_transition_returns_409(client, repo, principal):
    plan = _seed(repo, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=True)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "completed"}, headers=_auth())

    assert response.status_code == 409
    # Unchanged after a rejected transition.
    assert client.get(f"/meal-plans/{plan.id}", headers=_auth()).json()["status"] == "draft"


def test_patch_activating_empty_plan_returns_422(client, repo, principal):
    plan = _seed(repo, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=False)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": "active"}, headers=_auth())

    assert response.status_code == 422


def test_patch_unknown_or_unowned_plan_returns_404(client, repo, principal):
    other = _seed(repo, "someone-else", status=MealPlanStatus.ACTIVE, with_meal=True)

    missing = client.patch(
        "/meal-plans/00000000-0000-0000-0000-000000000000",
        json={"status": "completed"},
        headers=_auth(),
    )
    unowned = client.patch(f"/meal-plans/{other.id}", json={"status": "completed"}, headers=_auth())

    assert missing.status_code == 404
    assert unowned.status_code == 404


@pytest.mark.parametrize("bad_status", ["draft", "archived", ""])
def test_patch_rejects_invalid_target_status(client, repo, principal, bad_status):
    plan = _seed(repo, principal.user_id, status=MealPlanStatus.DRAFT, with_meal=True)

    response = client.patch(f"/meal-plans/{plan.id}", json={"status": bad_status}, headers=_auth())

    assert response.status_code == 422
