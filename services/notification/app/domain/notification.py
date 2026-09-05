"""The :class:`Notification` entity -- the record NTF-102 exists to persist.

A notification is immutable. Every state change (the user reads it, the push provider
acknowledges it) returns a *new* instance rather than mutating in place, so a value handed
to a template renderer or a push adapter cannot be changed underneath it, and so a store
write is always a whole-record write with no partial-update race.

The two mutable-looking fields are handled deliberately:

* ``channels`` is a tuple, order-preserving and de-duplicated at construction.
* ``payload`` is deep-frozen -- nested mappings become read-only views and nested sequences
  become tuples -- and is validated as JSON-native, so a notification that constructs is a
  notification the store can serialize. That check belongs here rather than in the codec:
  the domain refuses to hold a value it cannot round-trip.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.errors import InvalidNotification

_JSON_SCALARS = (str, int, float, bool)


def _freeze(value: Any, *, path: str) -> Any:
    """Return a deep, immutable, JSON-native copy of ``value``.

    ``path`` names the offending location so a rejection points at the actual field rather
    than at the payload as a whole.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidNotification(f"payload{path} must be finite, got {value!r}")
        return value
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidNotification(f"payload{path} keys must be strings, got {key!r}")
            frozen[key] = _freeze(item, path=f"{path}[{key!r}]")
        return MappingProxyType(frozen)
    if isinstance(value, Sequence):
        return tuple(_freeze(item, path=f"{path}[{index}]") for index, item in enumerate(value))
    raise InvalidNotification(f"payload{path} is not JSON-serializable: {type(value).__name__}")


def _normalize_channels(channels: Iterable[NotificationChannel]) -> tuple[NotificationChannel, ...]:
    """De-duplicate ``channels`` while preserving the caller's ordering."""
    seen: dict[NotificationChannel, None] = {}
    for channel in channels:
        seen[NotificationChannel(channel)] = None
    return tuple(seen)


def _as_utc(moment: datetime, *, name: str) -> datetime:
    """Require an aware datetime and express it in UTC.

    Naive datetimes are rejected rather than assumed to be UTC: the feed is ordered by this
    value, and silently guessing a timezone would mis-order a user's notifications.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise InvalidNotification(f"{name} must be timezone-aware")
    return moment.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Notification:
    """One thing worth telling a user about, addressed to one or more channels."""

    user_id: uuid.UUID
    type: NotificationType
    payload: Mapping[str, Any] = field(default_factory=dict)
    channels: tuple[NotificationChannel, ...] = (NotificationChannel.IN_APP,)
    status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", NotificationType(self.type))
        object.__setattr__(self, "status", DeliveryStatus(self.status))
        object.__setattr__(self, "payload", _freeze(dict(self.payload), path=""))

        channels = _normalize_channels(self.channels)
        if not channels:
            raise InvalidNotification("a notification must target at least one channel")
        object.__setattr__(self, "channels", channels)

        created_at = _as_utc(self.created_at, name="created_at")
        object.__setattr__(self, "created_at", created_at)

        if self.read_at is not None:
            read_at = _as_utc(self.read_at, name="read_at")
            if read_at < created_at:
                raise InvalidNotification("read_at cannot precede created_at")
            object.__setattr__(self, "read_at", read_at)

    @property
    def is_read(self) -> bool:
        """True once the user has seen this notification in the in-app feed."""
        return self.read_at is not None

    def targets(self, channel: NotificationChannel) -> bool:
        """True when this notification is meant to surface on ``channel``."""
        return channel in self.channels

    def mark_read(self, *, at: datetime | None = None) -> Notification:
        """Return a read copy, or ``self`` when it was already read.

        Idempotence matters: the feed API (NTF-105) is a client-driven endpoint that will be
        called twice on a double-tap, and re-reading must not move the original timestamp.
        """
        if self.is_read:
            return self
        return replace(self, read_at=at or datetime.now(UTC))

    def with_status(self, status: DeliveryStatus) -> Notification:
        """Return a copy carrying ``status`` -- how NTF-303 records provider receipts."""
        status = DeliveryStatus(status)
        if status is self.status:
            return self
        return replace(self, status=status)
