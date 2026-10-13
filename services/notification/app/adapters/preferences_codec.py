"""JSON codec for a stored :class:`~app.domain.preferences.NotificationPreferences` record.

Same principle as :mod:`app.adapters.codec`: the stored form is the wire form, camelCase, so
a record travels from Redis to a client through one mapping instead of two.

The mutes are stored as a **list of objects** rather than as ``"type:channel"`` strings or a
nested map. Composite string keys have to be parsed back apart, and every parser eventually
meets a value containing its own separator; a nested map (type -> [channels]) has two
representations of "nothing muted" (absent, and present-but-empty) that then have to be kept
equivalent everywhere. A flat list of ``{"type": ..., "channel": ...}`` has neither problem
and reads correctly in ``redis-cli`` without a decoder ring.

Decoding is forward-compatible in the same way as the notification codec -- unknown keys are
ignored so a newer replica does not crash an older one mid-deploy -- but strict about the
fields it knows: a preference record that cannot be understood raises rather than silently
degrading to "everything enabled", which would be an invisible reversal of the user's choice.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, time
from typing import Any

from app.domain.enums import NotificationChannel, NotificationType
from app.domain.errors import InvalidPreferences
from app.domain.preferences import Mute, NotificationPreferences
from app.domain.quiet_hours import QuietHours

TIME_FORMAT = "%H:%M"
"""Quiet-hours bounds are local wall-clock times to the minute -- no offset, no seconds."""


def format_time(value: time) -> str:
    """Render a quiet-hours bound as ``HH:MM``."""
    return value.strftime(TIME_FORMAT)


def parse_time(value: Any, *, name: str) -> time:
    """Parse an ``HH:MM`` wall-clock bound, rejecting anything else."""
    try:
        return datetime.strptime(str(value), TIME_FORMAT).time()
    except (ValueError, TypeError) as exc:
        raise InvalidPreferences(f"{name} must be a local time as HH:MM, got {value!r}") from exc


def _sorted_mutes(muted: frozenset[Mute]) -> list[dict[str, str]]:
    """Render the mutes in a deterministic order.

    Sorting is not cosmetic: a ``frozenset`` iterates in hash order, so an unsorted encoding
    would produce a different JSON string for the same preferences on different runs. That
    would make the stored record impossible to compare, diff, or assert on byte-for-byte.
    """
    return [
        {"type": notification_type.value, "channel": channel.value}
        for notification_type, channel in sorted(
            muted, key=lambda pair: (pair[0].value, pair[1].value)
        )
    ]


def quiet_hours_to_record(quiet_hours: QuietHours) -> dict[str, str]:
    """Reduce a quiet-hours window to its JSON-native record."""
    return {
        "start": format_time(quiet_hours.start),
        "end": format_time(quiet_hours.end),
        "timeZone": quiet_hours.time_zone,
    }


def quiet_hours_from_record(record: Mapping[str, Any]) -> QuietHours:
    """Rebuild a quiet-hours window from its JSON-native record."""
    if "timeZone" not in record:
        raise InvalidPreferences("quiet hours are missing 'timeZone'")
    return QuietHours(
        start=parse_time(_require(record, "start"), name="quietHours.start"),
        end=parse_time(_require(record, "end"), name="quietHours.end"),
        time_zone=str(record["timeZone"]),
    )


def to_record(preferences: NotificationPreferences) -> dict[str, Any]:
    """Reduce preferences to their JSON-native record."""
    return {
        "userId": str(preferences.user_id),
        "muted": _sorted_mutes(preferences.muted),
        "quietHours": (
            None
            if preferences.quiet_hours is None
            else quiet_hours_to_record(preferences.quiet_hours)
        ),
        "updatedAt": preferences.updated_at.isoformat(),
    }


def encode(preferences: NotificationPreferences) -> str:
    """Serialize preferences to the compact JSON string stored in Redis."""
    return json.dumps(to_record(preferences), separators=(",", ":"), ensure_ascii=False)


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise InvalidPreferences(f"stored preferences are missing {key!r}")
    return record[key]


def _as_mute(entry: Any) -> Mute:
    if not isinstance(entry, Mapping):
        raise InvalidPreferences(f"a mute must be an object, got {entry!r}")
    try:
        return (
            NotificationType(_require(entry, "type")),
            NotificationChannel(_require(entry, "channel")),
        )
    except ValueError as exc:
        raise InvalidPreferences(
            f"unknown notification type or channel in {dict(entry)!r}"
        ) from exc


def from_record(record: Mapping[str, Any]) -> NotificationPreferences:
    """Rebuild preferences from their JSON-native record."""
    muted = record.get("muted") or []
    if isinstance(muted, (str, bytes)) or not isinstance(muted, Sequence):
        raise InvalidPreferences(f"muted must be a list, got {muted!r}")

    quiet_hours = record.get("quietHours")
    if quiet_hours is not None and not isinstance(quiet_hours, Mapping):
        raise InvalidPreferences(f"quietHours must be an object or null, got {quiet_hours!r}")

    try:
        user_id = uuid.UUID(str(_require(record, "userId")))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidPreferences(f"userId is not a UUID: {record.get('userId')!r}") from exc

    try:
        updated_at = datetime.fromisoformat(str(_require(record, "updatedAt")))
    except (ValueError, TypeError) as exc:
        raise InvalidPreferences(
            f"updatedAt is not an ISO-8601 timestamp: {record.get('updatedAt')!r}"
        ) from exc

    return NotificationPreferences(
        user_id=user_id,
        muted=frozenset(_as_mute(entry) for entry in muted),
        quiet_hours=None if quiet_hours is None else quiet_hours_from_record(quiet_hours),
        updated_at=updated_at,
    )


def decode(raw: str | bytes) -> NotificationPreferences:
    """Parse a stored JSON string back into preferences."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidPreferences(f"stored preferences are not valid JSON: {exc}") from exc
    if not isinstance(record, Mapping):
        raise InvalidPreferences(f"stored preferences must be an object, got {record!r}")
    return from_record(record)
