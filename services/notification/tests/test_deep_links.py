"""The deep-link spelling shared with the mobile router (NTF-304)."""

from __future__ import annotations

from app.domain.deep_links import meal_deep_link, order_deep_link, plan_deep_link


def test_order_link_targets_the_order_screen() -> None:
    assert order_deep_link("2b7c1f6e-1f7a-4a1e-9b1b-6a0c1d2e3f40") == (
        "nutriplan://order/2b7c1f6e-1f7a-4a1e-9b1b-6a0c1d2e3f40"
    )


def test_plan_link_carries_an_optional_action() -> None:
    assert plan_deep_link("plan-1") == "nutriplan://plan/plan-1"
    assert plan_deep_link("plan-1", "manage") == "nutriplan://plan/plan-1/manage"
    assert plan_deep_link("plan-1", "renew") == "nutriplan://plan/plan-1/renew"


def test_meal_link_targets_the_meal_screen() -> None:
    assert meal_deep_link("meal-1") == "nutriplan://meal/meal-1"


def test_a_slash_in_an_id_does_not_create_an_extra_segment() -> None:
    """The mobile plan parser rejects a third segment, so the id must arrive encoded."""
    assert plan_deep_link("a/b", "manage") == "nutriplan://plan/a%2Fb/manage"
