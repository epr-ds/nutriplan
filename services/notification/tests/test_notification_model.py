"""The :class:`Notification` entity: what it accepts, refuses, and returns on change."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.errors import InvalidNotification, NotificationError
from app.domain.notification import Notification

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _notification(**overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "user_id": USER,
        "type": NotificationType.ORDER_CONFIRMED,
        "created_at": NOW,
    }
    return Notification(**(defaults | overrides))  # type: ignore[arg-type]


def test_defaults_are_an_unread_pending_in_app_notification() -> None:
    notification = _notification()

    assert notification.channels == (NotificationChannel.IN_APP,)
    assert notification.status is DeliveryStatus.PENDING
    assert notification.read_at is None
    assert notification.is_read is False
    assert isinstance(notification.id, uuid.UUID)


def test_each_notification_gets_its_own_id() -> None:
    assert _notification().id != _notification().id


def test_string_values_are_coerced_to_their_enum_members() -> None:
    notification = _notification(type="order_delivered", status="sent")

    assert notification.type is NotificationType.ORDER_DELIVERED
    assert notification.status is DeliveryStatus.SENT


def test_channels_are_deduplicated_in_the_order_given() -> None:
    notification = _notification(
        channels=(
            NotificationChannel.PUSH,
            NotificationChannel.IN_APP,
            NotificationChannel.PUSH,
        )
    )

    assert notification.channels == (NotificationChannel.PUSH, NotificationChannel.IN_APP)
    assert notification.targets(NotificationChannel.PUSH) is True


def test_a_notification_must_target_a_channel() -> None:
    with pytest.raises(InvalidNotification, match="at least one channel"):
        _notification(channels=())


def test_targets_is_false_for_a_channel_not_addressed() -> None:
    notification = _notification(channels=(NotificationChannel.IN_APP,))

    assert notification.targets(NotificationChannel.PUSH) is False


def test_created_at_is_normalized_to_utc() -> None:
    mexico_city = timezone(timedelta(hours=-6))
    notification = _notification(created_at=datetime(2026, 9, 5, 6, 0, tzinfo=mexico_city))

    assert notification.created_at == NOW
    assert notification.created_at.tzinfo is UTC


@pytest.mark.parametrize("field", ["created_at", "read_at"])
def test_naive_timestamps_are_refused(field: str) -> None:
    # Guessing a timezone would mis-order a user's feed, so it is refused outright.
    with pytest.raises(InvalidNotification, match="timezone-aware"):
        _notification(**{field: datetime(2026, 9, 5, 12, 0)})


def test_read_at_cannot_precede_created_at() -> None:
    with pytest.raises(InvalidNotification, match="cannot precede"):
        _notification(read_at=NOW - timedelta(seconds=1))


def test_read_at_may_equal_created_at() -> None:
    assert _notification(read_at=NOW).is_read is True


def test_mark_read_returns_a_read_copy_and_leaves_the_original_alone() -> None:
    notification = _notification()
    later = NOW + timedelta(minutes=5)

    read = notification.mark_read(at=later)

    assert read is not notification
    assert read.read_at == later
    assert read.is_read is True
    assert notification.read_at is None
    assert read.id == notification.id


def test_mark_read_is_idempotent() -> None:
    # The feed API is client-driven; a double-tap must not move the original timestamp.
    already = _notification().mark_read(at=NOW)

    assert already.mark_read(at=NOW + timedelta(hours=1)) is already


def test_with_status_returns_a_copy_and_is_a_no_op_when_unchanged() -> None:
    notification = _notification()

    delivered = notification.with_status(DeliveryStatus.DELIVERED)

    assert delivered.status is DeliveryStatus.DELIVERED
    assert notification.status is DeliveryStatus.PENDING
    assert delivered.with_status(DeliveryStatus.DELIVERED) is delivered


def test_read_state_and_delivery_status_move_independently() -> None:
    # A suppressed push is still recorded in-app, and can still be read there.
    suppressed = _notification(status=DeliveryStatus.SUPPRESSED).mark_read(at=NOW)

    assert suppressed.status is DeliveryStatus.SUPPRESSED
    assert suppressed.is_read is True


def test_the_entity_is_frozen() -> None:
    with pytest.raises(AttributeError):
        _notification().status = DeliveryStatus.SENT  # type: ignore[misc]


def test_the_payload_is_copied_from_the_caller_s_dict() -> None:
    source = {"orderId": "abc"}
    notification = _notification(payload=source)

    source["orderId"] = "mutated"

    assert notification.payload["orderId"] == "abc"


def test_nested_payload_values_are_deeply_immutable() -> None:
    notification = _notification(payload={"order": {"id": "abc"}, "items": [1, 2]})

    assert notification.payload["items"] == (1, 2)
    with pytest.raises(TypeError):
        notification.payload["order"]["id"] = "mutated"


def test_a_payload_that_could_not_be_stored_is_refused_at_construction() -> None:
    # The domain refuses to hold a value the store could not round-trip.
    with pytest.raises(InvalidNotification, match="not JSON-serializable"):
        _notification(payload={"when": datetime.now(UTC)})


def test_payload_keys_must_be_strings() -> None:
    with pytest.raises(InvalidNotification, match="keys must be strings"):
        _notification(payload={1: "one"})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_payload_numbers_are_refused(value: float) -> None:
    # json.dumps would happily emit NaN/Infinity, which no JSON parser must accept.
    with pytest.raises(InvalidNotification, match="must be finite"):
        _notification(payload={"score": value})


def test_the_rejection_names_the_offending_path() -> None:
    with pytest.raises(InvalidNotification, match=r"\['order'\]\['placedAt'\]"):
        _notification(payload={"order": {"placedAt": datetime.now(UTC)}})


def test_invalid_notification_is_both_a_domain_error_and_a_value_error() -> None:
    assert issubclass(InvalidNotification, NotificationError)
    assert issubclass(InvalidNotification, ValueError)


def test_order_types_are_recognisable_as_order_updates() -> None:
    assert NotificationType.ORDER_IN_TRANSIT.is_order_update is True
    assert NotificationType.MEAL_REMINDER.is_order_update is False


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (DeliveryStatus.PENDING, False),
        (DeliveryStatus.SENT, False),
        (DeliveryStatus.DELIVERED, True),
        (DeliveryStatus.FAILED, True),
        (DeliveryStatus.SUPPRESSED, True),
    ],
)
def test_terminal_statuses_are_the_ones_no_retry_can_change(
    status: DeliveryStatus, terminal: bool
) -> None:
    assert status.is_terminal is terminal


def test_order_types_cover_every_newsworthy_commerce_status() -> None:
    # NTF-202 maps order.status_changed onto a type by name; pending is deliberately absent.
    commerce_states = {"confirmed", "preparing", "in_transit", "delivered", "cancelled"}

    mapped = {t.value.removeprefix("order_") for t in NotificationType if t.is_order_update}

    assert mapped == commerce_states
