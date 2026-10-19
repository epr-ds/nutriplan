"""JSON codec for a stored :class:`~app.domain.device_token.DeviceToken` record.

Same rule as the other codecs in this package: the stored form is the wire form, camelCase,
so the registration API projects a stored record through one mapping instead of two.

The token itself is stored in full, not hashed. It has to be -- the delivery path hands it to
FCM/APNs verbatim, and a digest cannot be used as an address. What protects it is the store,
not the encoding: the record lives under the user's own namespace, is never returned by the
API, and is deleted the moment the token is revoked or the provider reports it dead.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain.device_token import DeviceToken
from app.domain.enums import DevicePlatform
from app.domain.errors import InvalidDeviceToken


def to_record(device: DeviceToken) -> dict[str, Any]:
    """Reduce a registration to its JSON-native record."""
    return {
        "id": str(device.id),
        "userId": str(device.user_id),
        "platform": device.platform.value,
        "token": device.token,
        "createdAt": device.created_at.isoformat(),
        "updatedAt": device.updated_at.isoformat(),
    }


def encode(device: DeviceToken) -> str:
    """Serialize a registration to the compact JSON string stored in Redis."""
    return json.dumps(to_record(device), separators=(",", ":"), ensure_ascii=False)


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise InvalidDeviceToken(f"stored device token is missing {key!r}")
    return record[key]


def _uuid(value: Any, *, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidDeviceToken(f"{name} is not a UUID: {value!r}") from exc


def _timestamp(value: Any, *, name: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise InvalidDeviceToken(f"{name} is not an ISO-8601 timestamp: {value!r}") from exc


def from_record(record: Mapping[str, Any]) -> DeviceToken:
    """Rebuild a registration from its JSON-native record."""
    try:
        platform = DevicePlatform(str(_require(record, "platform")))
    except ValueError as exc:
        raise InvalidDeviceToken(
            f"stored device token has an unknown platform: {record.get('platform')!r}"
        ) from exc

    return DeviceToken(
        id=_uuid(_require(record, "id"), name="id"),
        user_id=_uuid(_require(record, "userId"), name="userId"),
        platform=platform,
        token=str(_require(record, "token")),
        created_at=_timestamp(_require(record, "createdAt"), name="createdAt"),
        updated_at=_timestamp(_require(record, "updatedAt"), name="updatedAt"),
    )


def decode(raw: str | bytes) -> DeviceToken:
    """Parse a stored JSON string back into a registration."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidDeviceToken(f"stored device token is not valid JSON: {exc}") from exc
    if not isinstance(record, Mapping):
        raise InvalidDeviceToken(f"stored device token must be an object, got {record!r}")
    return from_record(record)
