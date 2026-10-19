"""One device's outcome for one notification -- the per-device receipt (NTF-305).

NTF-303 recorded a single status on the notification, which is the right shape for a user with
one phone and an untruth for a user with three. A notification that reached a tablet and failed
on a phone is neither ``SENT`` nor ``FAILED`` at the notification level; the honest answer is
one receipt per device, with the notification's own status a *rollup* that says "at least one
device accepted it".

The receipt names the **device, not the token**. That keeps a record which gets logged or dumped
from carrying a provider address, and the token is only ever needed at the moment of the send,
not afterwards. Receipts are internal: the feed exposes the rollup and nothing here is on the
wire contract. They expire with the notification they describe, because a receipt for a
notification nobody can read any more is only a leak with a timestamp.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.enums import DeliveryStatus, DevicePlatform
from app.domain.errors import InvalidPushReceipt

ACCEPTED_STATUS = DeliveryStatus.SENT
REFUSED_STATUS = DeliveryStatus.FAILED
"""The only two outcomes a receipt records: accepted by the provider, or refused by it."""


def _as_utc(value: datetime) -> datetime:
    """Require an aware timestamp and normalize it to UTC."""
    offset = value.tzinfo and value.tzinfo.utcoffset(value)
    if offset is None:
        raise InvalidPushReceipt("updated_at must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PushReceipt:
    """What one provider said about one notification sent to one device."""

    notification_id: uuid.UUID
    device_id: uuid.UUID
    platform: DevicePlatform
    status: DeliveryStatus
    updated_at: datetime
    message_id: str | None = None
    error: str | None = None
    pruned: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "platform", DevicePlatform(self.platform))
        except ValueError as exc:
            raise InvalidPushReceipt(f"unknown device platform {self.platform!r}") from exc

        status = DeliveryStatus(self.status)
        if status not in (ACCEPTED_STATUS, REFUSED_STATUS):
            raise InvalidPushReceipt(
                f"a receipt records {ACCEPTED_STATUS.value!r} or {REFUSED_STATUS.value!r}, "
                f"not {status.value!r}"
            )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "updated_at", _as_utc(self.updated_at))

    @property
    def accepted(self) -> bool:
        """True when the provider took the message."""
        return self.status is ACCEPTED_STATUS

    @classmethod
    def accepted_by(
        cls,
        notification_id: uuid.UUID,
        device_id: uuid.UUID,
        platform: DevicePlatform,
        *,
        message_id: str | None,
        now: datetime | None = None,
    ) -> PushReceipt:
        """Record that the provider accepted the message for this device."""
        return cls(
            notification_id=notification_id,
            device_id=device_id,
            platform=platform,
            status=ACCEPTED_STATUS,
            updated_at=now or datetime.now(UTC),
            message_id=message_id,
        )

    @classmethod
    def refused_by(
        cls,
        notification_id: uuid.UUID,
        device_id: uuid.UUID,
        platform: DevicePlatform,
        *,
        error: str,
        pruned: bool = False,
        now: datetime | None = None,
    ) -> PushReceipt:
        """Record that the provider refused the message, or the retry budget ran out."""
        return cls(
            notification_id=notification_id,
            device_id=device_id,
            platform=platform,
            status=REFUSED_STATUS,
            updated_at=now or datetime.now(UTC),
            error=error,
            pruned=pruned,
        )
