"""HRD-201: critical-path load-test scenarios for the NutriPlan API surface."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRIMARY_HARNESS = _REPO_ROOT / "load-tests" / "nutriplan.js"


def _harness_text() -> str:
    return _PRIMARY_HARNESS.read_text(encoding="utf-8")


def test_primary_harness_covers_the_auth_scenario() -> None:
    """HRD-201: critical paths start with an authenticated session (login + profile)."""
    text = _harness_text()
    assert "/auth/login" in text
    assert "access_token" in text


def test_primary_harness_covers_the_plan_scenario() -> None:
    """HRD-201: critical paths include the meal-plan read path."""
    text = _harness_text()
    assert "/api/meal-plans" in text


def test_primary_harness_covers_the_order_scenario() -> None:
    """HRD-201: critical paths include the order lifecycle (create → pay → track)."""
    text = _harness_text()
    assert "/orders" in text or "/api/orders" in text


def test_primary_harness_covers_the_notification_scenario() -> None:
    """HRD-201: critical paths include the notification fan-out (order status push)."""
    text = _harness_text()
    assert "/notifications" in text.lower() or "notification" in text.lower()
