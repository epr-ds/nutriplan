"""The closed vocabularies a notification is described by.

All three are ``StrEnum`` so a value serializes to its own wire form -- the codec can write
``notification.type`` straight into JSON and read it back by calling the enum, with no
mapping table to keep in sync.
"""

from __future__ import annotations

from enum import StrEnum


class NotificationType(StrEnum):
    """What happened, from the user's point of view.

    The ``ORDER_*`` members mirror the newsworthy states of Commerce's ``OrderStatus``
    (COM-106) one-for-one, so the NTF-202 consumer can map an ``order.status_changed``
    event onto a type by name rather than through a lookup table. ``pending`` has no member
    on purpose: an order entering its initial state is not news to the user.

    The ``MEAL_REMINDER`` / ``PLAN_ENDING`` members cover the P2 meal-plan reminders that
    NTF-203 schedules.
    """

    ORDER_CONFIRMED = "order_confirmed"
    ORDER_PREPARING = "order_preparing"
    ORDER_IN_TRANSIT = "order_in_transit"
    ORDER_DELIVERED = "order_delivered"
    ORDER_CANCELLED = "order_cancelled"
    MEAL_REMINDER = "meal_reminder"
    PLAN_ENDING = "plan_ending"

    @property
    def is_order_update(self) -> bool:
        """True for the order-lifecycle types fed by the P4 order-event stream."""
        return self.value.startswith("order_")


class NotificationChannel(StrEnum):
    """Where a notification is meant to surface.

    ``IN_APP`` is the durable feed this service owns; ``PUSH`` is the best-effort nudge
    handed to FCM/APNs (NTF-301). They are independent -- a notification can target either
    or both -- because NTF-404 gates push behind preferences and quiet hours while still
    recording the in-app copy.
    """

    IN_APP = "in_app"
    PUSH = "push"


class DeliveryStatus(StrEnum):
    """How far a notification got on its way to the user.

    This tracks *delivery*, not whether the user has looked at it -- read-state is
    ``Notification.read_at``, which moves independently. The progression is
    ``PENDING -> SENT -> DELIVERED``, with two ways to end early: ``FAILED`` once the
    bounded retries in NTF-303 are exhausted, and ``SUPPRESSED`` when a preference or a
    quiet-hours window (NTF-104) deliberately withheld it. Suppression is not an error, so
    it stays distinguishable from failure.
    """

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SUPPRESSED = "suppressed"

    @property
    def is_terminal(self) -> bool:
        """True once no further delivery attempt will change this status."""
        return self in {
            DeliveryStatus.DELIVERED,
            DeliveryStatus.FAILED,
            DeliveryStatus.SUPPRESSED,
        }
