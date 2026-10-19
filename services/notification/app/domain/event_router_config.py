"""Static routing configuration for event handlers (NTF-205).

This module provides the routing table that maps event types to handler import paths,
and functions to build the router and resolve handler instances from those paths.

The configuration is static: routing rules are deployment-time decisions, not runtime
decisions. This is by design: changing which events trigger which notifications is
a configuration change, not an in-flight one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from app.domain.event_router import EventRouter

if TYPE_CHECKING:
    from app.events.consumer import EventHandler

# =============================================================================
# Static routing table: event type → ordered list of handler import paths
# =============================================================================

ROUTING_TABLE: Mapping[str, Sequence[str]] = {
    "order.confirmed": [
        "app.application.order_status_consumer.OrderStatusConsumer",
    ],
    "order.status_changed": [
        "app.application.order_status_consumer.OrderStatusConsumer",
    ],
    # Phase 5: Meal reminder events (NTF-401)
    "meal.reminder.scheduled": [
        "app.application.meal_reminder_consumer.MealReminderConsumer",
    ],
    "meal.reminder.due": [
        "app.application.meal_reminder_consumer.MealReminderConsumer",
    ],
    "meal.reminder.cancelled": [
        "app.application.meal_reminder_consumer.MealReminderConsumer",
    ],
    # Phase 5: Plan ending events (NTF-402)
    "plan.ending.soon": [
        "app.application.plan_ending_consumer.PlanEndingConsumer",
    ],
    "plan.ended": [
        "app.application.plan_ending_consumer.PlanEndingConsumer",
    ],
    "plan.renewal.due": [
        "app.application.plan_ending_consumer.PlanEndingConsumer",
    ],
}
"""Static mapping from event type to handler import paths.

Each event type maps to an ordered list of handler fully-qualified names.
The dispatcher will call them in order; if one fails with EventError, the
chain stops (permanent failure). If it fails with anything else, the whole
event is retried (transient failure).

Known event types:
    order.confirmed    -- Order changed to CONFIRMED status
    order.status_changed -- Order changed to any other status
"""


# =============================================================================
# Builder functions
# =============================================================================


def build_router() -> EventRouter:
    """Build an EventRouter using the static ROUTING_TABLE.

    :return: EventRouter configured with ROUTING_TABLE mappings.
    """
    return EventRouter(ROUTING_TABLE)


def build_handler_registry() -> dict[str, EventHandler]:
    """Build a mapping of handler names to handler instances.

    The factory function instantiates each handler class with its dependencies.
    This returns actual instances ready for the dispatcher.

    :return: Mapping from handler import path to handler instance.
    """
    from app.events.factory import build_order_status_consumer

    handlers_by_name: dict[str, EventHandler] = {}

    # Build the order status consumer (our only handler type currently), sharing the one
    # wiring path in ``events.factory`` so push delivery cannot be forgotten here.
    order_status = build_order_status_consumer()

    # Map each configured handler path to the same instance
    # In this service, all event types route to OrderStatusConsumer
    for paths in ROUTING_TABLE.values():
        for path in paths:
            handlers_by_name[path] = order_status

    return handlers_by_name
