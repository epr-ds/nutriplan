"""HRD-401: backend localization audit — meal-reminder fallback copy is localized.

The notification copy engine ships a Spanish default catalog and an English secondary catalog
(NTF-401), and the reminder types were pinned by NTF-403. The backend localization audit's content
gate: when a meal-reminder event arrives without a ``mealName``, the consumer fabricates the
fallback from ``meal_type.title()`` — English copy — instead of a localized meal-type label, so an
untranslated string reaches the user's feed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.events.envelope import EventEnvelope

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")
MEAL_TYPE = "breakfast"


def _meal_event(meal_name: str | None) -> EventEnvelope:
    """One meal-reminder due event, with or without a ``mealName``."""
    data: dict[str, Any] = {
        "userId": str(USER),
        "mealId": str(uuid.uuid4()),
        "mealType": MEAL_TYPE,
        "scheduledTime": datetime.now(UTC).isoformat(),
    }
    if meal_name is not None:
        data["mealName"] = meal_name
    return EventEnvelope(
        schema_version=1,
        event_id=str(uuid.uuid4()),
        type="meal.reminder.due",
        occurred_at=datetime.now(UTC),
        data=data,
    )


def test_a_meal_reminder_without_a_meal_name_uses_localized_meal_type_copy(
    meal_reminder_consumer: Any,
) -> None:
    """HRD-401: the fallback meal-name must be a localized label, not English ``<type>.title()``."""
    meal_reminder_consumer.consumer.handle(_meal_event(None))

    notification = meal_reminder_consumer.feed(USER)[0]
    assert notification.payload["mealName"] == "Desayuno"
