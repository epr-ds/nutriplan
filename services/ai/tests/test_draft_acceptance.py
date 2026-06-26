"""Unit tests for accepting an optimized draft (AIA-405).

A draft is a proposal, not a commitment. When the user accepts it, :class:`PlanDraftAcceptor`
persists the proposed plan through the :class:`PlanWriter` port — re-statused from ``draft`` to a
committed ``active`` plan, forwarding the caller's Bearer token so the write is scoped to its owner
(mirroring how :class:`~app.optimization.gateway.PlanGateway` reads). The original plan is never
written, so declining a draft simply leaves the user's plan as it was. The real persistence adapter
(a dietary-service client) lands with the mobile/gateway slices; this ships the port plus an
in-memory adapter so the use case is exercised fully offline.
"""

from __future__ import annotations

from datetime import date

from app.optimization.acceptance import (
    InMemoryPlanWriter,
    PlanDraftAcceptor,
    build_plan_draft_acceptor,
)
from app.optimization.baseline import baseline_for
from app.optimization.commands import OptimizationGoal
from app.optimization.draft import PlanDraft
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.result import OptimizationOutcome

_OWNER = "owner-token"
_PLAN_ID = "11111111-1111-1111-1111-111111111111"
_GOAL = OptimizationGoal.INCREASE_PROTEIN


def _plan(*, protein: float, servings: float, status: str = "active") -> OptimizationPlan:
    nutrition = PlanNutrition(calories=400, protein=protein, carbs=45.0, fat=12.0, sugar=8.0)
    return OptimizationPlan(
        id=_PLAN_ID,
        name="Cutting Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=2000,
        status=status,
        meals=(
            OptimizationMeal(
                id="m1", meal_type="breakfast", servings=servings, nutrition=nutrition
            ),
        ),
        nutritional_summary=PlanNutritionSummary(
            total=nutrition,
            daily_average=nutrition,
            targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
        ),
    )


def _improved_draft() -> PlanDraft:
    original = _plan(protein=20.0, servings=1.0, status="active")
    optimized = _plan(protein=30.0, servings=2.0, status="active")
    return PlanDraft.from_outcome(
        OptimizationOutcome(
            original=original,
            optimized=optimized,
            baseline=baseline_for(original, _GOAL),
            optimized_value=30.0,
        )
    )


class TestPlanDraftAcceptor:
    def test_persists_the_proposed_plan_as_a_committed_plan(self) -> None:
        writer = InMemoryPlanWriter()
        draft = _improved_draft()

        committed = PlanDraftAcceptor(writer).accept(draft, token=_OWNER)

        assert committed.status == "active"
        assert committed.meals[0].servings == 2.0
        assert writer.saved(_PLAN_ID, token=_OWNER) == committed

    def test_does_not_write_the_original_plan(self) -> None:
        writer = InMemoryPlanWriter()
        draft = _improved_draft()

        PlanDraftAcceptor(writer).accept(draft, token=_OWNER)

        # The original is left exactly as it was — only the accepted proposal is persisted.
        assert draft.original.status == "active"
        assert draft.original.meals[0].servings == 1.0
        assert writer.saved(_PLAN_ID, token=_OWNER).meals[0].servings == 2.0

    def test_scopes_the_write_to_the_accepting_owner(self) -> None:
        writer = InMemoryPlanWriter()

        PlanDraftAcceptor(writer).accept(_improved_draft(), token=_OWNER)

        assert writer.saved(_PLAN_ID, token=_OWNER) is not None
        assert writer.saved(_PLAN_ID, token="someone-else") is None


class TestBuildPlanDraftAcceptor:
    def test_defaults_to_an_in_memory_writer(self) -> None:
        acceptor = build_plan_draft_acceptor()

        committed = acceptor.accept(_improved_draft(), token=_OWNER)

        assert committed.status == "active"
