from datetime import date

from app.db.mongo import MEAL_PLANS
from app.domain.meal_plan import (
    MacroTargets,
    MealPlan,
    MealPlanStatus,
    MealType,
    PlannedMeal,
)
from app.repositories.mongo_meal_plan_repository import MongoMealPlanRepository


def _plan(**overrides) -> MealPlan:
    defaults = dict(
        user_id="user-1",
        name="Cutting week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
    )
    defaults.update(overrides)
    return MealPlan(**defaults)


def test_insert_and_get_roundtrip(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    plan = _plan(
        macro_targets=MacroTargets(protein_grams=150, carbs_grams=180, fat_grams=60),
        meals=[
            PlannedMeal(meal_type=MealType.BREAKFAST, recipe_id="r1", servings=1.5, day_index=0)
        ],
    )
    repo.add(plan)

    fetched = repo.get("user-1", plan.id)
    assert fetched is not None
    assert fetched.id == plan.id
    assert fetched.name == "Cutting week"
    assert fetched.status == MealPlanStatus.DRAFT.value
    assert fetched.start_date == date(2026, 1, 1)
    assert fetched.end_date == date(2026, 1, 7)
    assert fetched.daily_calorie_target == 2000
    assert fetched.macro_targets is not None
    assert fetched.macro_targets.protein_grams == 150
    assert len(fetched.meals) == 1
    assert fetched.meals[0].meal_type == MealType.BREAKFAST.value
    assert fetched.meals[0].recipe_id == "r1"
    assert fetched.meals[0].servings == 1.5
    assert fetched.meals[0].day_index == 0


def test_get_is_owner_scoped(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    plan = _plan(user_id="owner")
    repo.add(plan)

    assert repo.get("someone-else", plan.id) is None
    assert repo.get("owner", plan.id) is not None


def test_persisted_document_uses_id_as_underscore_id(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    plan = _plan()
    repo.add(plan)

    raw = mongo_db[MEAL_PLANS].find_one({"_id": plan.id})
    assert raw is not None
    assert raw["_id"] == plan.id
    assert "id" not in raw
    assert raw["userId"] == "user-1"
    # Optional/unset fields are omitted rather than stored as null.
    assert "dietaryType" not in raw
    assert "macroTargets" not in raw


def test_list_for_user_returns_only_owner_plans(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    repo.add(_plan(user_id="owner", name="A"))
    repo.add(_plan(user_id="owner", name="B"))
    repo.add(_plan(user_id="other", name="C"))

    plans = repo.list_for_user("owner")

    assert {p.name for p in plans} == {"A", "B"}
    assert all(p.user_id == "owner" for p in plans)


def test_list_for_user_filters_by_status(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    repo.add(_plan(user_id="u", name="draft-one"))  # defaults to DRAFT
    repo.add(_plan(user_id="u", name="active-one", status=MealPlanStatus.ACTIVE))
    repo.add(_plan(user_id="u", name="active-two", status=MealPlanStatus.ACTIVE))

    active = repo.list_for_user("u", status=MealPlanStatus.ACTIVE)

    assert {p.name for p in active} == {"active-one", "active-two"}
    assert all(p.status == MealPlanStatus.ACTIVE.value for p in active)


def test_list_for_user_paginates_with_skip_and_limit(mongo_db):
    repo = MongoMealPlanRepository(mongo_db[MEAL_PLANS])
    for i in range(5):
        repo.add(_plan(user_id="u", name=f"plan-{i}"))

    page1 = repo.list_for_user("u", skip=0, limit=2)
    page2 = repo.list_for_user("u", skip=2, limit=2)
    page3 = repo.list_for_user("u", skip=4, limit=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    # Pages are disjoint and together cover every plan (correct skip/limit).
    ids = {p.id for p in page1} | {p.id for p in page2} | {p.id for p in page3}
    assert len(ids) == 5
