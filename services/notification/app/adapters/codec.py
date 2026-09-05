"""JSON codec for a stored notification.

The stored form is the wire form: camelCase keys matching what the NTF-105 feed API will
publish, so the record can be read straight out of Redis and serialized to a client without
a second mapping. Times are ISO-8601 with an explicit offset; ids and enums are strings.

Decoding is deliberately **forward-compatible**: unknown top-level keys are ignored rather
than rejected, so a newer replica that writes an extra field does not crash an older one
mid-deploy. It is *not* lenient about the fields it does know -- a malformed id, an
unrecognized enum value, or a missing required key raises
:class:`~app.domain.errors.InvalidNotification`, because silently dropping such a record
would hide data corruption behind an empty feed.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.errors import InvalidNotification
from app.domain.notification import Notification


def _plain(value: Any) -> Any:
    """Undo the domain's deep-freeze so ``json.dumps`` can handle the payload.

    ``Notification`` stores nested mappings as read-only views and nested sequences as
    tuples; neither is JSON-serializable as-is (a ``mappingproxy`` raises outright).
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def to_record(notification: Notification) -> dict[str, Any]:
    """Reduce a notification to its JSON-native record."""
    return {
        "id": str(notification.id),
        "userId": str(notification.user_id),
        "type": notification.type.value,
        "payload": _plain(notification.payload),
        "channels": [channel.value for channel in notification.channels],
        "status": notification.status.value,
        "createdAt": notification.created_at.isoformat(),
        "readAt": notification.read_at.isoformat() if notification.read_at else None,
    }


def encode(notification: Notification) -> str:
    """Serialize a notification to the compact JSON string stored in Redis."""
    return json.dumps(to_record(notification), separators=(",", ":"), ensure_ascii=False)


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise InvalidNotification(f"stored notification is missing {key!r}")
    return record[key]


def _as_uuid(value: Any, *, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidNotification(f"{name} is not a UUID: {value!r}") from exc


def _as_datetime(value: Any, *, name: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise InvalidNotification(f"{name} is not an ISO-8601 timestamp: {value!r}") from exc


def _as_enum(enum: type, value: Any, *, name: str) -> Any:
    try:
        return enum(value)
    except ValueError as exc:
        raise InvalidNotification(f"{name} is not a known value: {value!r}") from exc


def from_record(record: Mapping[str, Any]) -> Notification:
    """Rebuild a notification from its JSON-native record."""
    channels = _require(record, "channels")
    if isinstance(channels, (str, bytes)) or not isinstance(channels, Sequence):
        raise InvalidNotification(f"channels must be a list, got {channels!r}")

    payload = record.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise InvalidNotification(f"payload must be an object, got {payload!r}")

    read_at = record.get("readAt")
    return Notification(
        id=_as_uuid(_require(record, "id"), name="id"),
        user_id=_as_uuid(_require(record, "userId"), name="userId"),
        type=_as_enum(NotificationType, _require(record, "type"), name="type"),
        payload=payload,
        channels=tuple(
            _as_enum(NotificationChannel, channel, name="channel") for channel in channels
        ),
        status=_as_enum(DeliveryStatus, _require(record, "status"), name="status"),
        created_at=_as_datetime(_require(record, "createdAt"), name="createdAt"),
        read_at=None if read_at is None else _as_datetime(read_at, name="readAt"),
    )


def decode(raw: str | bytes) -> Notification:
    """Parse a stored JSON string back into a notification."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidNotification(f"stored notification is not valid JSON: {exc}") from exc
    if not isinstance(record, Mapping):
        raise InvalidNotification(f"stored notification must be an object, got {record!r}")
    return from_record(record)
