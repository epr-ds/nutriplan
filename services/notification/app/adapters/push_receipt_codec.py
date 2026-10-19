"""JSON codec for a stored :class:`~app.domain.push_receipt.PushReceipt` (NTF-305).

Same rule as the other codecs in this package: the stored form is the wire form, camelCase, so
a receipt is one mapping rather than two. The device is named by its id, never its token, so a
receipt can be read out of Redis without exposing a provider address.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain.enums import DeliveryStatus, DevicePlatform
from app.domain.errors import InvalidPushReceipt
from app.domain.push_receipt import PushReceipt


def to_record(receipt: PushReceipt) -> dict[str, Any]:
    """Reduce a receipt to its JSON-native record."""
    return {
        "notificationId": str(receipt.notification_id),
        "deviceId": str(receipt.device_id),
        "platform": receipt.platform.value,
        "status": receipt.status.value,
        "messageId": receipt.message_id,
        "error": receipt.error,
        "pruned": receipt.pruned,
        "updatedAt": receipt.updated_at.isoformat(),
    }


def encode(receipt: PushReceipt) -> str:
    """Serialize a receipt to the compact JSON string stored in Redis."""
    return json.dumps(to_record(receipt), separators=(",", ":"), ensure_ascii=False)


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise InvalidPushReceipt(f"stored push receipt is missing {key!r}")
    return record[key]


def _uuid(value: Any, *, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidPushReceipt(f"{name} is not a UUID: {value!r}") from exc


def _timestamp(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise InvalidPushReceipt(f"updatedAt is not an ISO-8601 timestamp: {value!r}") from exc


def from_record(record: Mapping[str, Any]) -> PushReceipt:
    """Rebuild a receipt from its JSON-native record."""
    try:
        platform = DevicePlatform(str(_require(record, "platform")))
    except ValueError as exc:
        raise InvalidPushReceipt(
            f"stored push receipt has an unknown platform: {record.get('platform')!r}"
        ) from exc
    try:
        status = DeliveryStatus(str(_require(record, "status")))
    except ValueError as exc:
        raise InvalidPushReceipt(
            f"stored push receipt has an unknown status: {record.get('status')!r}"
        ) from exc

    return PushReceipt(
        notification_id=_uuid(_require(record, "notificationId"), name="notificationId"),
        device_id=_uuid(_require(record, "deviceId"), name="deviceId"),
        platform=platform,
        status=status,
        updated_at=_timestamp(_require(record, "updatedAt")),
        message_id=record.get("messageId"),
        error=record.get("error"),
        pruned=bool(record.get("pruned", False)),
    )


def decode(raw: str | bytes) -> PushReceipt:
    """Parse a stored JSON string back into a receipt."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidPushReceipt(f"stored push receipt is not valid JSON: {exc}") from exc
    if not isinstance(record, Mapping):
        raise InvalidPushReceipt(f"stored push receipt must be an object, got {record!r}")
    return from_record(record)
