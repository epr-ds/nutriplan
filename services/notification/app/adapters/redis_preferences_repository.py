"""The Redis-backed preferences store.

A single ``GET``/``SET`` per user against ``{ns}:v1:p:{user_id}`` -- there is no index to keep
and no page to slice, because preferences are only ever read for one known user at a time
(the delivery path knows whose notification it is holding; the settings screen knows who is
logged in).

**The ``SET`` deliberately carries no ``EX``.** Every other key this service writes expires,
so writing one that does not looks like an omission; it is the opposite. A muted notification
type that switched itself back on thirty days later -- silently, at a moment with no
connection to anything the user did -- would be a bug the user experiences as the app
ignoring them. The absence of a TTL here is asserted by a test that reads ``TTL`` back from a
live server, so it cannot be "tidied up" by someone matching the surrounding style.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Protocol

from app.adapters import preferences_codec
from app.adapters.keys import NotificationKeys
from app.domain.preferences import NotificationPreferences


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str) -> Any: ...
    def mget(self, keys: Iterable[str]) -> list[Any]: ...


class RedisPreferencesRepository:
    """Adapt a redis-py-style client to the preferences persistence port."""

    def __init__(self, client: RedisLike, *, keys: NotificationKeys | None = None) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()

    @classmethod
    def from_url(
        cls, url: str, *, keys: NotificationKeys | None = None
    ) -> RedisPreferencesRepository:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys)

    @staticmethod
    def _text(value: Any) -> str | None:
        """Normalize a redis-py reply to ``str`` whether or not decoding is enabled."""
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    def get(self, user_id: uuid.UUID) -> NotificationPreferences | None:
        raw = self._text(self._client.get(self._keys.preferences(user_id)))
        return None if raw is None else preferences_codec.decode(raw)

    def save(self, preferences: NotificationPreferences) -> NotificationPreferences:
        self._client.set(
            self._keys.preferences(preferences.user_id),
            preferences_codec.encode(preferences),
        )
        return preferences
