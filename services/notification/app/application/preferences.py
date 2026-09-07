"""Read and replace a user's notification preferences (NTF-104).

This layer exists to keep one decision from leaking outward. Preferences are **stored** as a
sparse deny-list of mutes (see :mod:`app.domain.preferences`), because that is the only shape
that survives the notification catalogue growing. But a settings screen needs the opposite: a
complete, ordered list of rows it can render as toggles without knowing which types exist.

So the matrix is materialized here, on the way out, and collapsed back to mutes on the way in.
Clients see a full matrix and never learn that "absent means enabled"; the store keeps its
sparse form and a new ``NotificationType`` is on for everybody the day it ships.

The write is a **full replacement**, not a patch. A partial update of a matrix whose rows the
client may not know about is ambiguous in a way that cannot be resolved from the request: if a
client running last month's build omits a row, "leave it alone" and "reset it to default" are
both defensible, and picking either silently does the wrong thing for somebody. Replacement
says exactly what the user's settings are now, and any type the client did not mention returns
to its default (enabled) -- which is also what a client that has never heard of that type is
already showing the user.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.enums import NotificationChannel, NotificationType
from app.domain.errors import InvalidPreferences
from app.domain.preferences import Mute, NotificationPreferences
from app.domain.quiet_hours import QuietHours
from app.domain.repositories import PreferencesRepository


@dataclass(frozen=True, slots=True)
class TypePreference:
    """One row of the materialized matrix: a type and its per-channel switches."""

    type: NotificationType
    in_app: bool = True
    push: bool = True

    def enabled_on(self, channel: NotificationChannel) -> bool:
        """True when this row leaves ``channel`` switched on."""
        return self.in_app if channel is NotificationChannel.IN_APP else self.push

    def mutes(self) -> tuple[Mute, ...]:
        """The (type, channel) pairs this row switches off -- the sparse form of the row."""
        return tuple(
            (self.type, channel) for channel in NotificationChannel if not self.enabled_on(channel)
        )


@dataclass(frozen=True, slots=True)
class PreferenceMatrix:
    """A user's preferences as a client sees them: every type, in declaration order."""

    user_id: uuid.UUID
    types: tuple[TypePreference, ...]
    quiet_hours: QuietHours | None
    updated_at: datetime

    @classmethod
    def from_preferences(cls, preferences: NotificationPreferences) -> PreferenceMatrix:
        """Expand a stored deny-list into the full matrix.

        Iteration is over ``NotificationType`` itself rather than over the stored mutes, which
        is what makes a newly added type appear -- enabled -- without a migration.
        """
        return cls(
            user_id=preferences.user_id,
            types=tuple(
                TypePreference(
                    type=notification_type,
                    in_app=not preferences.is_muted(notification_type, NotificationChannel.IN_APP),
                    push=not preferences.is_muted(notification_type, NotificationChannel.PUSH),
                )
                for notification_type in NotificationType
            ),
            quiet_hours=preferences.quiet_hours,
            updated_at=preferences.updated_at,
        )


def _collapse(rows: Iterable[TypePreference]) -> frozenset[Mute]:
    """Reduce matrix rows to the sparse set of mutes, rejecting duplicate rows.

    A repeated type is refused rather than resolved last-wins: two rows for one type carry two
    different answers to the same question, and quietly honouring one of them would leave the
    user looking at a screen that disagrees with what was saved.
    """
    seen: set[NotificationType] = set()
    mutes: set[Mute] = set()
    for row in rows:
        notification_type = NotificationType(row.type)
        if notification_type in seen:
            raise InvalidPreferences(f"duplicate preference row for {notification_type.value!r}")
        seen.add(notification_type)
        mutes.update(row.mutes())
    return frozenset(mutes)


class NotificationPreferenceService:
    """Read and replace one user's notification preferences."""

    def __init__(self, repository: PreferencesRepository) -> None:
        self._repository = repository

    def get(self, user_id: uuid.UUID) -> PreferenceMatrix:
        """Return the caller's preferences, defaulting to everything enabled.

        A user who has never opened the settings screen has no stored record, which is not an
        error and must not be a 404: they *do* have preferences -- the defaults -- and the
        screen needs to render them.
        """
        stored = self._repository.get(user_id) or NotificationPreferences.defaults(user_id)
        return PreferenceMatrix.from_preferences(stored)

    def replace(
        self,
        user_id: uuid.UUID,
        *,
        types: Sequence[TypePreference],
        quiet_hours: QuietHours | None,
    ) -> PreferenceMatrix:
        """Replace the caller's preferences wholesale and return the stored result."""
        preferences = NotificationPreferences(
            user_id=user_id,
            muted=_collapse(types),
            quiet_hours=quiet_hours,
            updated_at=datetime.now(UTC),
        )
        return PreferenceMatrix.from_preferences(self._repository.save(preferences))
