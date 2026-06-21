"""DPL-103 API tests for ``GET /meal-plans`` (Mongo-free via dependency overrides).

The service is overridden with an in-memory repository and the token verifier with a stub, so the
test exercises the real router, query-parameter validation, auth dependency, owner scoping and the
summary projection without MongoDB or network access.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_meal_plan_service, get_token_verifier
from app.application.meal_plan_service import MealPlanService
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.domain.meal_plan import MealPlan, MealPlanStatus
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
    name: str,
    status: MealPlanStatus = MealPlanStatus.DRAFT,
) -> MealPlan:
    plan = MealPlan(
        user_id=user_id,
        name=name,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=status,
    )
    repo.add(plan)
    return plan


def test_list_requires_authentication(client):
    assert client.get("/meal-plans").status_code == 401


def test_list_returns_only_callers_plans_as_summaries(client, repo, principal):
    _seed(repo, principal.user_id, "Mine A")
    _seed(repo, principal.user_id, "Mine B")
    _seed(repo, "someone-else", "Theirs")

    response = client.get("/meal-plans", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert {d["name"] for d in data} == {"Mine A", "Mine B"}
    # Summary projection shape (camelCase, contract MealPlanSummaryResponse).
    assert set(data[0]) == {"id", "name", "startDate", "endDate", "status"}


def test_list_summary_excludes_detail_and_owner_fields(client, repo, principal):
    _seed(repo, principal.user_id, "Mine")

    item = client.get("/meal-plans", headers=_auth()).json()[0]

    assert "dailyCalorieTarget" not in item
    assert "meals" not in item
    assert "userId" not in item


def test_list_filters_by_status(client, repo, principal):
    _seed(repo, principal.user_id, "d1", MealPlanStatus.DRAFT)
    _seed(repo, principal.user_id, "a1", MealPlanStatus.ACTIVE)
    _seed(repo, principal.user_id, "a2", MealPlanStatus.ACTIVE)

    response = client.get("/meal-plans", params={"status": "active"}, headers=_auth())

    assert response.status_code == 200
    assert {d["name"] for d in response.json()} == {"a1", "a2"}


def test_list_rejects_status_outside_contract_enum(client, repo, principal):
    # The contract restricts the filter to active/completed/saved; draft must be rejected.
    response = client.get("/meal-plans", params={"status": "draft"}, headers=_auth())
    assert response.status_code == 422


def test_list_paginates_with_page_and_limit(client, repo, principal):
    for i in range(5):
        _seed(repo, principal.user_id, f"p{i}")

    page1 = client.get("/meal-plans", params={"page": 1, "limit": 2}, headers=_auth()).json()
    page2 = client.get("/meal-plans", params={"page": 2, "limit": 2}, headers=_auth()).json()
    page3 = client.get("/meal-plans", params={"page": 3, "limit": 2}, headers=_auth()).json()

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    ids = {d["id"] for d in page1 + page2 + page3}
    assert len(ids) == 5


def test_list_rejects_limit_over_maximum(client):
    assert client.get("/meal-plans", params={"limit": 101}, headers=_auth()).status_code == 422


def test_list_rejects_non_positive_page(client):
    assert client.get("/meal-plans", params={"page": 0}, headers=_auth()).status_code == 422


def test_list_returns_empty_array_when_no_plans(client):
    response = client.get("/meal-plans", headers=_auth())
    assert response.status_code == 200
    assert response.json() == []
