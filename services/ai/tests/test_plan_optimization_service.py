"""Unit tests for the plan-optimization application layer (AIA-401).

These pin the seam established by the ``POST /ai/optimize-plan`` slice: a :class:`PlanGateway`
port that loads a caller-owned plan (forwarding the Bearer token so ownership is enforced
downstream, mirroring how the gateway does JWT verification — AIA-804), an in-memory adapter for
offline tests, and a stub :class:`PlanOptimizationService` that returns the loaded plan unchanged.
Real optimization (baseline metrics, constrained edits, re-scoring) fills this seam in AIA-402-405.
"""

from __future__ import annotations

from datetime import date

from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.service import PlanOptimizationService, build_plan_optimization_service

_OWNER = "owner-token"
_PLAN_ID = "11111111-1111-1111-1111-111111111111"


def _plan(plan_id: str = _PLAN_ID) -> OptimizationPlan:
    return OptimizationPlan(
        id=plan_id,
        name="Cutting Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status="active",
        meals=(
            OptimizationMeal(
                id="m1",
                meal_type="breakfast",
                servings=1.0,
                nutrition=PlanNutrition(
                    calories=400, protein=20.0, carbs=45.0, fat=12.0, sugar=8.0
                ),
            ),
        ),
        nutritional_summary=PlanNutritionSummary(
            total=PlanNutrition(calories=400, protein=20.0, carbs=45.0, fat=12.0, sugar=8.0),
            daily_average=PlanNutrition(
                calories=400, protein=20.0, carbs=45.0, fat=12.0, sugar=8.0
            ),
            targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
        ),
    )


def _command(plan_id: str = _PLAN_ID) -> OptimizePlanCommand:
    return OptimizePlanCommand(plan_id=plan_id, goal=OptimizationGoal.BALANCE_MACROS)


class TestInMemoryPlanGateway:
    def test_returns_a_plan_owned_by_the_caller(self) -> None:
        gateway = InMemoryPlanGateway()
        gateway.add(_plan(), owner=_OWNER)

        assert gateway.get_plan(_PLAN_ID, token=_OWNER) == _plan()

    def test_hides_an_unknown_plan(self) -> None:
        gateway = InMemoryPlanGateway()
        gateway.add(_plan(), owner=_OWNER)

        assert gateway.get_plan("22222222-2222-2222-2222-222222222222", token=_OWNER) is None

    def test_hides_a_plan_owned_by_another_caller(self) -> None:
        # Not-found and not-owned are deliberately indistinguishable -> both 404 (no enumeration).
        gateway = InMemoryPlanGateway()
        gateway.add(_plan(), owner=_OWNER)

        assert gateway.get_plan(_PLAN_ID, token="someone-else") is None

    def test_can_be_seeded_from_a_mapping(self) -> None:
        gateway = InMemoryPlanGateway({_OWNER: [_plan()]})

        assert gateway.get_plan(_PLAN_ID, token=_OWNER) == _plan()


class _RecordingGateway:
    """Captures the (plan_id, token) it was asked for and returns a fixed result."""

    def __init__(self, result: OptimizationPlan | None) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def get_plan(self, plan_id: str, *, token: str) -> OptimizationPlan | None:
        self.calls.append((plan_id, token))
        return self.result


class TestPlanOptimizationService:
    def test_returns_the_loaded_plan_unchanged(self) -> None:
        # AIA-401 is the seam: the "optimized" plan is the loaded plan (optimization = AIA-402+).
        gateway = _RecordingGateway(_plan())
        service = PlanOptimizationService(gateway=gateway)

        assert service.optimize(_command(), token=_OWNER) == _plan()

    def test_forwards_the_plan_id_and_token_to_the_gateway(self) -> None:
        gateway = _RecordingGateway(_plan())
        service = PlanOptimizationService(gateway=gateway)

        service.optimize(_command(), token=_OWNER)

        assert gateway.calls == [(_PLAN_ID, _OWNER)]

    def test_returns_none_when_the_plan_is_absent_or_not_owned(self) -> None:
        gateway = _RecordingGateway(None)
        service = PlanOptimizationService(gateway=gateway)

        assert service.optimize(_command(), token=_OWNER) is None


class TestBuildPlanOptimizationService:
    def test_defaults_to_an_empty_gateway(self) -> None:
        # Until a real dietary-service adapter lands (AIA-402), production loads no plans -> 404.
        service = build_plan_optimization_service()

        assert service.optimize(_command(), token=_OWNER) is None
