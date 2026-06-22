"""DPL-302: plan-level nutritional summary (``summarize_plan_nutrition``).

Pure, Mongo-free tests for the domain service that rolls a meal plan's per-meal nutrition (computed
by DPL-301 and embedded on each ``PlannedMeal``) up into a :class:`NutritionalSummary`: the
**total** across the plan, the **daily average** over the plan's date span, and the plan's
**targets**. They pin down the date-span divisor (inclusive), the **half-up** rounding rule
(calories to a whole number, macros to one decimal place), and the "unknown stays ``None``" rule (a
nutrient no meal reports is never silently reported as ``0``).
"""

from datetime import date

from app.domain.meal_plan import (
    MacroTargets,
    MealPlan,
    MealType,
    NutritionalInfo,
    PlannedMeal,
)
from app.domain.nutrition import summarize_plan_nutrition


def _meal(nutritional_info: NutritionalInfo | None) -> PlannedMeal:
    return PlannedMeal(
        meal_type=MealType.BREAKFAST,
        recipe_id="recipe-1",
        servings=1.0,
        nutritional_info=nutritional_info,
    )


def _plan(
    *,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 1, 7),
    daily_calorie_target: int = 2000,
    macro_targets: MacroTargets | None = None,
    meals=(),
) -> MealPlan:
    return MealPlan(
        user_id="user-1",
        name="Plan",
        start_date=start,
        end_date=end,
        daily_calorie_target=daily_calorie_target,
        macro_targets=macro_targets,
        meals=list(meals),
    )


def test_total_sums_each_meals_nutrition():
    plan = _plan(
        meals=[
            _meal(NutritionalInfo(calories=420, protein=30.0, carbs=40.0, fat=10.0, sugar=5.0)),
            _meal(NutritionalInfo(calories=300, protein=10.5, carbs=20.0, fat=8.0, sugar=2.0)),
        ]
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 720
    assert summary.total.protein == 40.5
    assert summary.total.carbs == 60.0
    assert summary.total.fat == 18.0
    assert summary.total.sugar == 7.0


def test_total_macro_sum_avoids_float_drift():
    # 9.9 + 9.9 is 19.799999... in binary float; exact-decimal summation must give 19.8.
    plan = _plan(meals=[_meal(NutritionalInfo(protein=9.9)), _meal(NutritionalInfo(protein=9.9))])

    summary = summarize_plan_nutrition(plan)

    assert summary.total.protein == 19.8


def test_daily_average_divides_total_by_date_span():
    # Jan 1..Jan 7 inclusive = 7 days.
    plan = _plan(
        start=date(2026, 1, 1),
        end=date(2026, 1, 7),
        meals=[
            _meal(NutritionalInfo(calories=400, protein=40.0)),
            _meal(NutritionalInfo(calories=300, protein=30.0)),
        ],
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 700
    assert summary.daily_average.calories == 100  # 700 / 7
    assert summary.daily_average.protein == 10.0  # 70.0 / 7


def test_daily_average_rounds_half_up():
    # Jan 1..Jan 2 inclusive = 2 days; 365 / 2 = 182.5 -> 183, 29.7 / 2 = 14.85 -> 14.9.
    plan = _plan(
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        meals=[_meal(NutritionalInfo(calories=365, protein=29.7))],
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 365
    assert summary.daily_average.calories == 183
    assert summary.daily_average.protein == 14.9


def test_single_day_plan_average_equals_total():
    day = date(2026, 3, 3)
    plan = _plan(start=day, end=day, meals=[_meal(NutritionalInfo(calories=500, protein=33.3))])

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 500
    assert summary.daily_average.calories == 500
    assert summary.daily_average.protein == 33.3


def test_targets_reflect_plan_calorie_and_macro_targets():
    plan = _plan(
        daily_calorie_target=2200,
        macro_targets=MacroTargets(
            protein_grams=150, carbs_grams=180, fat_grams=60, sugar_grams=40
        ),
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.targets.calories == 2200
    assert summary.targets.protein == 150
    assert summary.targets.carbs == 180
    assert summary.targets.fat == 60
    assert summary.targets.sugar == 40


def test_targets_macros_are_none_without_macro_targets():
    plan = _plan(daily_calorie_target=1800, macro_targets=None)

    summary = summarize_plan_nutrition(plan)

    assert summary.targets.calories == 1800
    assert summary.targets.protein is None
    assert summary.targets.carbs is None
    assert summary.targets.fat is None
    assert summary.targets.sugar is None


def test_empty_plan_has_unknown_totals_but_keeps_targets():
    plan = _plan(meals=[], daily_calorie_target=2000)

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories is None
    assert summary.total.protein is None
    assert summary.daily_average.calories is None
    assert summary.daily_average.protein is None
    assert summary.targets.calories == 2000


def test_nutrient_absent_from_every_meal_stays_none():
    plan = _plan(
        meals=[
            _meal(NutritionalInfo(calories=400, protein=20.0)),
            _meal(NutritionalInfo(calories=300, protein=15.0)),
        ]
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 700
    assert summary.total.protein == 35.0
    assert summary.total.carbs is None
    assert summary.total.fat is None
    assert summary.total.sugar is None
    assert summary.daily_average.carbs is None


def test_partial_nutrient_sums_only_known_meals():
    # One meal reports protein, the other does not: the known value is kept, not erased to None.
    plan = _plan(
        meals=[
            _meal(NutritionalInfo(calories=200, protein=10.0)),
            _meal(NutritionalInfo(calories=200)),
        ]
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 400
    assert summary.total.protein == 10.0


def test_meal_without_nutritional_info_is_skipped():
    plan = _plan(
        meals=[
            _meal(NutritionalInfo(calories=400, protein=20.0)),
            _meal(None),
        ]
    )

    summary = summarize_plan_nutrition(plan)

    assert summary.total.calories == 400
    assert summary.total.protein == 20.0
