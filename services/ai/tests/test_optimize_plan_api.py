"""HTTP tests for ``POST /ai/optimize-plan`` — the transport edge (AIA-401, AIA-405).

This slice owns Bearer auth, request validation (``planId`` UUID + ``goal`` enum), the caller-owned
plan lookup (a missing or not-owned plan -> ``404``), and the ``MealPlanResponse`` envelope. The
optimization service is overridden with one backed by an in-memory gateway and a pass-through
optimizer, so these tests run offline and pin the request -> command mapping and the response
projection without depending on AIA-403's edit behavior (pinned in ``test_plan_optimizer.py``).
AIA-405 adds the draft projection: an improving optimization is returned with ``status: draft`` and
the stored original is left untouched.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_plan_optimization_service
from app.api.optimization import _to_command
from app.api.schemas import OptimizePlanRequest
from app.main import app
from app.optimization.commands import OptimizationGoal
from app.optimization.gateway import InMemoryPlanGateway
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.service import PlanOptimizationService

client = TestClient(app)

_TOKEN = "test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_PROBLEM_JSON = "application/problem+json"
_PLAN_ID = "11111111-1111-1111-1111-111111111111"
_UNKNOWN_PLAN_ID = "99999999-9999-9999-9999-999999999999"


class _PassThroughOptimizer:
    """Keeps the edge tests about transport + projection: the plan is returned unedited."""

    def optimize(self, plan: OptimizationPlan, goal: OptimizationGoal) -> OptimizationPlan:
        return plan


class _ImprovingOptimizer:
    """Returns a strictly-better plan (more protein) so the outcome is a real, improving draft."""

    def optimize(self, plan: OptimizationPlan, goal: OptimizationGoal) -> OptimizationPlan:
        better = PlanNutrition(calories=400, protein=80.0, carbs=45.0, fat=12.0, sugar=8.0)
        return OptimizationPlan(
            id=plan.id,
            name=plan.name,
            start_date=plan.start_date,
            end_date=plan.end_date,
            daily_calorie_target=plan.daily_calorie_target,
            status=plan.status,
            meals=(
                OptimizationMeal(id="m1", meal_type="breakfast", servings=3.0, nutrition=better),
            ),
            nutritional_summary=PlanNutritionSummary(
                total=better,
                daily_average=better,
                targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
            ),
        )


def _plan() -> OptimizationPlan:
    return OptimizationPlan(
        id=_PLAN_ID,
        name="Cutting Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status="active",
        meals=(
            OptimizationMeal(
                id="m1",
                meal_type="breakfast",
                servings=1.5,
                nutrition=PlanNutrition(
                    calories=400, protein=20.5, carbs=45.0, fat=12.0, sugar=8.0
                ),
            ),
        ),
        nutritional_summary=PlanNutritionSummary(
            total=PlanNutrition(calories=400, protein=20.5, carbs=45.0, fat=12.0, sugar=8.0),
            daily_average=PlanNutrition(calories=57, protein=2.9, carbs=6.4, fat=1.7, sugar=1.1),
            targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
        ),
    )


def _service() -> PlanOptimizationService:
    gateway = InMemoryPlanGateway()
    gateway.add(_plan(), owner=_TOKEN)
    return PlanOptimizationService(gateway=gateway, optimizer=_PassThroughOptimizer())


@pytest.fixture(autouse=True)
def _override_service():
    app.dependency_overrides[get_plan_optimization_service] = _service
    yield
    app.dependency_overrides.pop(get_plan_optimization_service, None)


def _body(**overrides: object) -> dict[str, object]:
    return {"planId": _PLAN_ID, "goal": "balance_macros", **overrides}


def test_requires_bearer_token() -> None:
    response = client.post("/ai/optimize-plan", json=_body())

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["status"] == 401


def test_plan_id_is_required() -> None:
    response = client.post("/ai/optimize-plan", json={"goal": "balance_macros"}, headers=_AUTH)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)


def test_plan_id_must_be_a_uuid() -> None:
    response = client.post("/ai/optimize-plan", json=_body(planId="not-a-uuid"), headers=_AUTH)

    assert response.status_code == 422


def test_rejects_an_unknown_goal() -> None:
    response = client.post("/ai/optimize-plan", json=_body(goal="make_it_tasty"), headers=_AUTH)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "goal",
    ["balance_macros", "increase_protein", "reduce_calories", "increase_satisfaction"],
)
def test_accepts_every_documented_goal(goal: str) -> None:
    response = client.post("/ai/optimize-plan", json=_body(goal=goal), headers=_AUTH)

    assert response.status_code == 200


def test_goal_is_optional() -> None:
    response = client.post("/ai/optimize-plan", json={"planId": _PLAN_ID}, headers=_AUTH)

    assert response.status_code == 200


def test_unknown_plan_returns_404() -> None:
    response = client.post("/ai/optimize-plan", json=_body(planId=_UNKNOWN_PLAN_ID), headers=_AUTH)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)
    assert response.json()["status"] == 404


def test_plan_owned_by_another_caller_returns_404() -> None:
    # Same valid plan id, different bearer -> indistinguishable from not-found (no enumeration).
    response = client.post(
        "/ai/optimize-plan",
        json=_body(),
        headers={"Authorization": "Bearer someone-else"},
    )

    assert response.status_code == 404


def test_returns_meal_plan_shape() -> None:
    body = client.post("/ai/optimize-plan", json=_body(), headers=_AUTH).json()

    assert body["id"] == _PLAN_ID
    assert body["name"] == "Cutting Week"
    assert body["startDate"] == "2026-01-01"
    assert body["endDate"] == "2026-01-07"
    assert body["dailyCalorieTarget"] == 2000
    assert body["status"] == "active"
    assert body["nutritionalSummary"]["targets"]["calories"] == 2000
    assert body["nutritionalSummary"]["total"]["protein"] == 20.5
    [meal] = body["meals"]
    assert meal["id"] == "m1"
    assert meal["mealType"] == "breakfast"
    assert meal["servings"] == 1.5
    assert meal["nutritionalInfo"]["calories"] == 400
    assert meal["nutritionalInfo"]["protein"] == 20.5
    # Plan reads do not expand the recipe (matches the dietary MealPlanResponse projection).
    assert meal["recipe"] is None


def test_optimized_plan_is_returned_as_a_draft() -> None:
    gateway = InMemoryPlanGateway()
    gateway.add(_plan(), owner=_TOKEN)
    app.dependency_overrides[get_plan_optimization_service] = lambda: PlanOptimizationService(
        gateway=gateway, optimizer=_ImprovingOptimizer()
    )

    body = client.post(
        "/ai/optimize-plan", json=_body(goal="increase_protein"), headers=_AUTH
    ).json()

    assert body["status"] == "draft"
    assert body["meals"][0]["servings"] == 3.0
    # An optimize call never overwrites the stored plan — the original is left untouched.
    stored = gateway.get_plan(_PLAN_ID, token=_TOKEN)
    assert stored.status == "active"
    assert stored.meals[0].servings == 1.5


def test_projects_a_plan_without_a_summary_as_null() -> None:
    gateway = InMemoryPlanGateway()
    gateway.add(
        OptimizationPlan(
            id=_PLAN_ID,
            name="Bare",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            daily_calorie_target=1800,
            status="draft",
        ),
        owner=_TOKEN,
    )
    app.dependency_overrides[get_plan_optimization_service] = lambda: PlanOptimizationService(
        gateway=gateway, optimizer=_PassThroughOptimizer()
    )

    body = client.post("/ai/optimize-plan", json={"planId": _PLAN_ID}, headers=_AUTH).json()

    assert body["status"] == "draft"
    assert body["meals"] == []
    assert body["nutritionalSummary"] is None


def test_to_command_maps_plan_id_and_goal() -> None:
    request = OptimizePlanRequest.model_validate({"planId": _PLAN_ID, "goal": "increase_protein"})

    command = _to_command(request)

    assert command.plan_id == _PLAN_ID
    assert command.goal is not None
    assert command.goal.value == "increase_protein"


def test_to_command_allows_a_missing_goal() -> None:
    request = OptimizePlanRequest.model_validate({"planId": _PLAN_ID})

    command = _to_command(request)

    assert command.goal is None
