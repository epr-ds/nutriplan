"""An in-process preferences store for dev, CI, and tests.

Like the in-memory notification store, this keeps records as **encoded JSON** rather than as
live objects, so the codec runs on the dev path too and a record that could not survive a
round-trip fails locally instead of only in production. It also means a caller cannot mutate
stored state by holding on to the object it saved.
"""

from __future__ import annotations

import uuid

from app.adapters import preferences_codec
from app.domain.preferences import NotificationPreferences


class InMemoryPreferencesRepository:
    """A dict-backed :class:`~app.domain.repositories.PreferencesRepository`."""

    def __init__(self) -> None:
        self._records: dict[str, str] = {}

    def get(self, user_id: uuid.UUID) -> NotificationPreferences | None:
        raw = self._records.get(str(user_id))
        return None if raw is None else preferences_codec.decode(raw)

    def save(self, preferences: NotificationPreferences) -> NotificationPreferences:
        self._records[str(preferences.user_id)] = preferences_codec.encode(preferences)
        return preferences
