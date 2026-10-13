"""What a user has chosen *not* to be told about (NTF-104, AC1).

The shape of this record is the important decision, and it is deliberately **a deny-list of
mutes, never a materialized allow-matrix**.

A full matrix -- one stored flag per (type, channel) pair -- looks tidier and fails badly the
first time the catalogue grows. ``NotificationType`` gains members over time (NTF-203 adds the
meal-plan reminders; anything later adds its own), and a matrix written last release simply
does not mention the new ones. Reading "absent" as *disabled* silently mutes a brand-new
notification for every existing user, which produces no error, no log line, and no complaint
anyone can act on. Reading "absent" as *enabled* works -- but that is a deny-list wearing a
matrix's clothes, at several times the storage and with an invariant nobody can see.

So only the exceptions are stored. **Absent means enabled**, a new notification type is on for
everybody the day it ships, and the record stays proportional to what the user actually
changed. The API materializes the complete matrix on the way out (see
:mod:`app.application.preferences`), so clients never have to know any of this.

Quiet hours gate **push only**, and that asymmetry is intentional. The in-app feed is pull-based
and makes no sound; withholding an entry from it at 23:00 would not spare the user anything,
and the notification would then either appear in the morning out of chronological order or be
lost outright. Quiet hours exist to stop the phone buzzing, not to hide information the user
came looking for.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from app.domain.enums import NotificationChannel, NotificationType
from app.domain.errors import InvalidPreferences
from app.domain.quiet_hours import QuietHours

Mute = tuple[NotificationType, NotificationChannel]
"""One switched-off (type, channel) pair -- the only thing this record actually stores."""


def _normalize_mutes(mutes: Iterable[Mute]) -> frozenset[Mute]:
    """Coerce every pair to real enum members so a decoded record compares equal to a built one."""
    normalized: set[Mute] = set()
    for pair in mutes:
        try:
            notification_type, channel = pair
        except (TypeError, ValueError) as exc:
            raise InvalidPreferences(
                f"a mute must be a (type, channel) pair, got {pair!r}"
            ) from exc
        try:
            normalized.add((NotificationType(notification_type), NotificationChannel(channel)))
        except ValueError as exc:
            raise InvalidPreferences(f"unknown notification type or channel in {pair!r}") from exc
    return frozenset(normalized)


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    """One user's notification opt-outs and quiet-hours window."""

    user_id: uuid.UUID
    muted: frozenset[Mute] = frozenset()
    quiet_hours: QuietHours | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "muted", _normalize_mutes(self.muted))
        offset = self.updated_at.tzinfo and self.updated_at.tzinfo.utcoffset(self.updated_at)
        if offset is None:
            raise InvalidPreferences("updated_at must be timezone-aware")
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))

    @classmethod
    def defaults(cls, user_id: uuid.UUID) -> NotificationPreferences:
        """Everything enabled, no quiet hours -- what a user who has never opened the screen has.

        Returned instead of ``None`` wherever preferences are missing, so the delivery path has
        exactly one shape to reason about and "has never set preferences" cannot become a
        separate branch that quietly behaves differently from "has set them to the defaults".
        """
        return cls(user_id=user_id)

    # -- queries -----------------------------------------------------------------

    def is_muted(self, notification_type: NotificationType, channel: NotificationChannel) -> bool:
        """True when the user has explicitly switched this (type, channel) pair off."""
        return (NotificationType(notification_type), NotificationChannel(channel)) in self.muted

    def in_quiet_hours(self, at: datetime | None = None) -> bool:
        """True when ``at`` falls inside the user's quiet-hours window."""
        if self.quiet_hours is None:
            return False
        return self.quiet_hours.covers(at or datetime.now(UTC))

    def allows(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        *,
        at: datetime | None = None,
    ) -> bool:
        """True when a notification of this type may go out on this channel right now."""
        if self.is_muted(notification_type, channel):
            return False
        if channel is NotificationChannel.PUSH and self.in_quiet_hours(at):
            return False
        return True

    def permitted_channels(
        self,
        notification_type: NotificationType,
        channels: Iterable[NotificationChannel],
        *,
        at: datetime | None = None,
    ) -> tuple[NotificationChannel, ...]:
        """Filter ``channels`` down to the ones this user still accepts, preserving order."""
        return tuple(
            channel for channel in channels if self.allows(notification_type, channel, at=at)
        )

    def channels_for(self, notification_type: NotificationType) -> frozenset[NotificationChannel]:
        """Every channel this type is enabled on, ignoring the clock.

        Quiet hours are excluded on purpose: this answers "what has the user switched on?",
        which is what a settings screen renders. Folding a time-dependent suppression into it
        would make the toggles flicker off every night.
        """
        return frozenset(
            channel
            for channel in NotificationChannel
            if not self.is_muted(notification_type, channel)
        )

    # -- builders ----------------------------------------------------------------

    def muting(
        self, notification_type: NotificationType, channel: NotificationChannel
    ) -> NotificationPreferences:
        """Return a copy with one more (type, channel) pair switched off."""
        pair = (NotificationType(notification_type), NotificationChannel(channel))
        return replace(self, muted=self.muted | {pair}, updated_at=datetime.now(UTC))

    def unmuting(
        self, notification_type: NotificationType, channel: NotificationChannel
    ) -> NotificationPreferences:
        """Return a copy with one (type, channel) pair switched back on."""
        pair = (NotificationType(notification_type), NotificationChannel(channel))
        return replace(self, muted=self.muted - {pair}, updated_at=datetime.now(UTC))

    def with_quiet_hours(self, quiet_hours: QuietHours | None) -> NotificationPreferences:
        """Return a copy with the quiet-hours window set, replaced, or cleared."""
        return replace(self, quiet_hours=quiet_hours, updated_at=datetime.now(UTC))
