"""DPL-102 domain unit tests: the MealPlan.create() factory and its invariants."""

from datetime import date

import pytest

from app.domain.errors import MealPlanDateRangeError
from app.domain.meal_plan import DietaryType, MacroTargets, MealPlan, MealPlanStatus


def test_create_defaults_to_draft_with_generated_id():
    plan = MealPlan.create(
        user_id="u1",
        name="Cutting week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )

    assert plan.id
    assert plan.user_id == "u1"
    assert plan.status == MealPlanStatus.DRAFT.value
    assert plan.meals == []
    assert plan.created_at is not None
    assert plan.updated_at is not None


def test_create_accepts_optional_targets():
    plan = MealPlan.create(
        user_id="u1",
        name="Keto",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=1800,
        macro_targets=MacroTargets(protein_grams=150, carbs_grams=40, fat_grams=120),
        dietary_type=DietaryType.KETO,
    )

    assert plan.macro_targets is not None
    assert plan.macro_targets.protein_grams == 150
    assert plan.dietary_type == DietaryType.KETO.value


def test_create_allows_single_day_plan():
    plan = MealPlan.create(
        user_id="u1",
        name="One day",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=1800,
    )

    assert plan.start_date == plan.end_date


def test_create_rejects_end_before_start():
    with pytest.raises(MealPlanDateRangeError):
        MealPlan.create(
            user_id="u1",
            name="Backwards",
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 1),
            daily_calorie_target=2000,
        )
