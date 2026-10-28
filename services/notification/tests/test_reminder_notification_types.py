"""NTF-403: plan-reminder notification types — meal time + plan ending (backend).

Re-verifies the reminder notification types the plan-remaining story ships: meal-time reminders
and plan-ending reminders each get copy in both locales, a deep link to the target screen, and a
render that fails loudly when the producer payload lacks a declared variable.
"""

from __future__ import annotations

import re

import pytest

from app.adapters.in_memory_notification_template_store import InMemoryNotificationTemplateStore
from app.application.templates import DEFAULT_NOTIFICATION_TEMPLATES, NotificationTemplateService
from app.domain.deep_links import meal_deep_link, plan_deep_link
from app.domain.enums import NotificationType
from app.domain.errors import MissingTemplateVariableError

_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _bare(text: str) -> str:
    return _PLACEHOLDER.sub("", text).strip()


def _service() -> NotificationTemplateService:
    return NotificationTemplateService(
        InMemoryNotificationTemplateStore(DEFAULT_NOTIFICATION_TEMPLATES)
    )


def _template(notification_type: NotificationType, locale):
    for template in DEFAULT_NOTIFICATION_TEMPLATES:
        if template.id == notification_type.value and template.locale.value == str(locale):
            return template
    return None


def test_meal_reminder_copy_covers_meal_time_in_both_locales() -> None:
    es = _template(NotificationType.MEAL_REMINDER, locale="es")
    en = _template(NotificationType.MEAL_REMINDER, locale="en")

    assert es is not None and en is not None
    assert "Recordatorio de comida" in es.title
    assert "Meal reminder" in en.title
    assert "$mealName" in es.body and "$deepLink" in es.body
    assert "$mealName" in en.body and "$deepLink" in en.body


def test_plan_ending_copy_covers_the_plan_end_in_both_locales() -> None:
    es = _template(NotificationType.PLAN_ENDING, locale="es")
    en = _template(NotificationType.PLAN_ENDING, locale="en")

    assert es is not None and en is not None
    assert "Tu plan se acaba pronto" in es.title
    assert "Your plan ends soon" in en.title
    assert "$planType" in es.body and "$endingDate" in es.body and "$deepLink" in es.body
    assert "$planType" in en.body and "$endingDate" in en.body and "$deepLink" in en.body


def test_the_reminder_deep_links_point_at_the_target_screen() -> None:
    assert meal_deep_link("meal-1") == "nutriplan://meal/meal-1"
    assert plan_deep_link("plan-1") == "nutriplan://plan/plan-1"
    assert plan_deep_link("plan-1", action="manage") == "nutriplan://plan/plan-1/manage"


def test_a_reminder_render_missing_a_declared_variable_is_a_bug() -> None:
    service = _service()

    with pytest.raises(MissingTemplateVariableError) as exc:
        service.render(
            NotificationType.MEAL_REMINDER,
            locale="es",
            variables={"mealName": "Oatmeal"},
        )

    assert "deepLink" in str(exc.value)

    with pytest.raises(MissingTemplateVariableError) as exc2:
        service.render(
            NotificationType.PLAN_ENDING,
            locale="en",
            variables={"planType": "weekly", "endingDate": "2026-11-01"},
        )

    assert "deepLink" in str(exc2.value)


def test_an_unhandled_reminder_type_is_not_in_the_catalog() -> None:
    assert NotificationType.MEAL_REMINDER.is_order_update is False
    assert NotificationType.PLAN_ENDING.is_order_update is False
