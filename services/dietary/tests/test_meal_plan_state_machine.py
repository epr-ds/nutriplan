"""DPL-106 domain unit tests: the MealPlan lifecycle state machine.

Allowed transitions: ``draft -> active -> {completed, saved}`` (completed/saved are terminal).
Activating a plan additionally requires it to hold at least one meal. Illegal transitions raise
:class:`IllegalStateTransitionError`; a contentless activation raises
:class:`EmptyMealPlanActivationError`.
"""

from datetime import date

import pytest

from app.domain.errors import (
    EmptyMealPlanActivationError,
    IllegalStateTransitionError,
)
from app.domain.meal_plan import (
    MealPlan,
    MealPlanStatus,
    MealType,
    PlannedMeal,
)


def _meal() -> PlannedMeal:
    return PlannedMeal(meal_type=MealType.BREAKFAST, recipe_id="r1", servings=1.0)


def _plan(*, status: MealPlanStatus = MealPlanStatus.DRAFT, with_meal: bool = False) -> MealPlan:
    return MealPlan(
        user_id="u1",
        name="Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status=status,
        meals=[_meal()] if with_meal else [],
    )


def test_draft_activates_when_it_has_a_meal():
    plan = _plan(status=MealPlanStatus.DRAFT, with_meal=True)

    plan.transition_to(MealPlanStatus.ACTIVE)

    assert plan.status == MealPlanStatus.ACTIVE.value


def test_active_can_complete():
    plan = _plan(status=MealPlanStatus.ACTIVE, with_meal=True)

    plan.transition_to(MealPlanStatus.COMPLETED)

    assert plan.status == MealPlanStatus.COMPLETED.value


def test_active_can_be_saved():
    plan = _plan(status=MealPlanStatus.ACTIVE, with_meal=True)

    plan.transition_to(MealPlanStatus.SAVED)

    assert plan.status == MealPlanStatus.SAVED.value


def test_transition_bumps_updated_at():
    plan = _plan(status=MealPlanStatus.ACTIVE, with_meal=True)
    before = plan.updated_at

    plan.transition_to(MealPlanStatus.COMPLETED)

    assert plan.updated_at > before


def test_intent_methods_match_transitions():
    plan = _plan(status=MealPlanStatus.DRAFT, with_meal=True)
    plan.activate()
    assert plan.status == MealPlanStatus.ACTIVE.value
    plan.complete()
    assert plan.status == MealPlanStatus.COMPLETED.value

    saved = _plan(status=MealPlanStatus.ACTIVE, with_meal=True)
    saved.save()
    assert saved.status == MealPlanStatus.SAVED.value


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (MealPlanStatus.DRAFT, MealPlanStatus.COMPLETED),
        (MealPlanStatus.DRAFT, MealPlanStatus.SAVED),
        (MealPlanStatus.DRAFT, MealPlanStatus.DRAFT),
        (MealPlanStatus.ACTIVE, MealPlanStatus.DRAFT),
        (MealPlanStatus.ACTIVE, MealPlanStatus.ACTIVE),
        (MealPlanStatus.COMPLETED, MealPlanStatus.ACTIVE),
        (MealPlanStatus.COMPLETED, MealPlanStatus.SAVED),
        (MealPlanStatus.SAVED, MealPlanStatus.ACTIVE),
        (MealPlanStatus.SAVED, MealPlanStatus.COMPLETED),
    ],
)
def test_illegal_transition_raises_and_leaves_status_unchanged(start, target):
    plan = _plan(status=start, with_meal=True)

    with pytest.raises(IllegalStateTransitionError):
        plan.transition_to(target)

    assert plan.status == start.value


def test_activating_without_a_meal_is_rejected():
    plan = _plan(status=MealPlanStatus.DRAFT, with_meal=False)

    with pytest.raises(EmptyMealPlanActivationError):
        plan.transition_to(MealPlanStatus.ACTIVE)

    assert plan.status == MealPlanStatus.DRAFT.value


def test_empty_meal_activation_is_distinct_from_illegal_transition():
    # An empty-plan activation is a *precondition* failure on a structurally-legal transition,
    # so it must not be reported as an illegal transition.
    plan = _plan(status=MealPlanStatus.DRAFT, with_meal=False)

    assert not issubclass(EmptyMealPlanActivationError, IllegalStateTransitionError)
    with pytest.raises(EmptyMealPlanActivationError):
        plan.activate()
