"""The JSON codec: the stored form is the wire form, and it survives a round trip."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters import codec
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.errors import InvalidNotification
from app.domain.notification import Notification

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _notification(**overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "user_id": USER,
        "type": NotificationType.ORDER_IN_TRANSIT,
        "created_at": NOW,
        "payload": {"orderId": "abc", "eta": {"minutes": 12}, "items": [1, 2]},
        "channels": (NotificationChannel.IN_APP, NotificationChannel.PUSH),
    }
    return Notification(**(defaults | overrides))  # type: ignore[arg-type]


def test_a_notification_survives_a_round_trip() -> None:
    notification = _notification(status=DeliveryStatus.SENT, read_at=NOW + timedelta(minutes=3))

    assert codec.decode(codec.encode(notification)) == notification


def test_an_unread_notification_round_trips_with_a_null_read_at() -> None:
    notification = _notification()

    assert codec.to_record(notification)["readAt"] is None
    assert codec.decode(codec.encode(notification)).read_at is None


def test_the_record_uses_the_camel_case_wire_shape() -> None:
    # The stored record is what NTF-105 will publish, so it is written in the API's casing.
    record = codec.to_record(_notification())

    assert set(record) == {
        "id",
        "userId",
        "type",
        "payload",
        "channels",
        "status",
        "createdAt",
        "readAt",
    }
    assert record["userId"] == str(USER)
    assert record["type"] == "order_in_transit"
    assert record["channels"] == ["in_app", "push"]
    assert record["status"] == "pending"


def test_timestamps_are_iso_8601_with_an_explicit_offset() -> None:
    record = codec.to_record(_notification())

    assert record["createdAt"] == "2026-09-05T12:00:00+00:00"


def test_the_frozen_payload_is_serialized_back_to_plain_json() -> None:
    # The domain stores nested mappings as read-only views, which json.dumps cannot handle.
    payload = json.loads(codec.encode(_notification()))["payload"]

    assert payload == {"orderId": "abc", "eta": {"minutes": 12}, "items": [1, 2]}


def test_the_encoded_form_is_compact() -> None:
    assert ", " not in codec.encode(_notification())


def test_non_ascii_payloads_survive_unescaped() -> None:
    notification = _notification(payload={"title": "Tu pedido está en camino"})

    assert "está" in codec.encode(notification)
    assert codec.decode(codec.encode(notification)).payload["title"] == "Tu pedido está en camino"


def test_decoding_accepts_bytes() -> None:
    notification = _notification()

    assert codec.decode(codec.encode(notification).encode("utf-8")) == notification


def test_unknown_fields_are_ignored() -> None:
    # Forward compatibility: a newer replica may write fields this one has never heard of.
    record = codec.to_record(_notification()) | {"deliveredAt": "2026-09-05T12:01:00+00:00"}

    assert codec.from_record(record).id == uuid.UUID(record["id"])


@pytest.mark.parametrize("missing", ["id", "userId", "type", "channels", "status", "createdAt"])
def test_a_missing_required_field_is_an_error(missing: str) -> None:
    # Dropping a corrupt record would hide the corruption behind a silently short feed.
    record = codec.to_record(_notification())
    del record[missing]

    with pytest.raises(InvalidNotification, match=f"missing '{missing}'"):
        codec.from_record(record)


def test_an_absent_payload_decodes_as_empty() -> None:
    record = codec.to_record(_notification(payload={}))
    del record["payload"]

    assert codec.from_record(record).payload == {}


def test_an_absent_read_at_decodes_as_unread() -> None:
    record = codec.to_record(_notification())
    del record["readAt"]

    assert codec.from_record(record).is_read is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "not-a-uuid", "id is not a UUID"),
        ("userId", "not-a-uuid", "userId is not a UUID"),
        ("type", "order_teleported", "type is not a known value"),
        ("status", "half-sent", "status is not a known value"),
        ("channels", ["carrier-pigeon"], "channel is not a known value"),
        ("createdAt", "yesterday", "createdAt is not an ISO-8601 timestamp"),
        ("readAt", "soon", "readAt is not an ISO-8601 timestamp"),
    ],
)
def test_a_malformed_field_is_an_error(field: str, value: object, message: str) -> None:
    record = codec.to_record(_notification()) | {field: value}

    with pytest.raises(InvalidNotification, match=message):
        codec.from_record(record)


def test_channels_must_be_a_list_not_a_bare_string() -> None:
    record = codec.to_record(_notification()) | {"channels": "in_app"}

    with pytest.raises(InvalidNotification, match="channels must be a list"):
        codec.from_record(record)


def test_a_payload_that_is_not_an_object_is_an_error() -> None:
    record = codec.to_record(_notification()) | {"payload": ["nope"]}

    with pytest.raises(InvalidNotification, match="payload must be an object"):
        codec.from_record(record)


def test_garbage_in_the_store_is_reported_as_such() -> None:
    with pytest.raises(InvalidNotification, match="not valid JSON"):
        codec.decode("{definitely not json")


def test_a_json_scalar_is_not_a_notification() -> None:
    with pytest.raises(InvalidNotification, match="must be an object"):
        codec.decode("42")
