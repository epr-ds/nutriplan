"""An in-process device-token store for dev, CI, and tests.

Records are kept as **encoded JSON**, as in the other in-memory adapters, so the codec runs
on the dev path too and a value that could not survive a round-trip fails locally rather than
only against Redis. Callers also cannot mutate stored state by holding on to an object.

The token index is keyed by the exact pair ``(platform, token)``. That pair is the record's
identity (see :mod:`app.domain.device_token`), which is what makes a launch-time re-register a
refresh instead of a second row.
"""

from __future__ import annotations

import uuid

from app.adapters import device_token_codec
from app.domain.device_token import DeviceToken, normalize_token
from app.domain.enums import DevicePlatform


class InMemoryDeviceTokenRepository:
    """A dict-backed :class:`~app.domain.repositories.DeviceTokenRepository`."""

    def __init__(self) -> None:
        self._records: dict[uuid.UUID, str] = {}
        self._tokens: dict[tuple[str, str], uuid.UUID] = {}
        self._users: dict[uuid.UUID, set[uuid.UUID]] = {}

    @staticmethod
    def _key(platform: DevicePlatform, token: str) -> tuple[str, str]:
        return (DevicePlatform(platform).value, normalize_token(token))

    def find_by_token(self, platform: DevicePlatform, token: str) -> DeviceToken | None:
        device_id = self._tokens.get(self._key(platform, token))
        return None if device_id is None else self._load(device_id)

    def get(self, device_id: uuid.UUID, *, user_id: uuid.UUID) -> DeviceToken | None:
        device = self._load(device_id)
        if device is None or not device.belongs_to(user_id):
            return None
        return device

    def list_for_user(self, user_id: uuid.UUID) -> list[DeviceToken]:
        devices = [
            device
            for device_id in self._users.get(user_id, set())
            if (device := self._load(device_id)) is not None and device.belongs_to(user_id)
        ]
        return sorted(devices, key=lambda device: (device.created_at, str(device.id)), reverse=True)

    def upsert(self, device: DeviceToken) -> DeviceToken:
        key = self._key(device.platform, device.token)

        previous_id = self._tokens.get(key)
        if previous_id is not None and previous_id != device.id:
            self._remove(previous_id)

        stored = self._load(device.id)
        if stored is not None:
            if (stored.platform, stored.token) != (device.platform, device.token):
                self._tokens.pop(self._key(stored.platform, stored.token), None)
            if stored.user_id != device.user_id:
                self._users.get(stored.user_id, set()).discard(device.id)

        self._records[device.id] = device_token_codec.encode(device)
        self._tokens[key] = device.id
        self._users.setdefault(device.user_id, set()).add(device.id)
        return device

    def delete(self, device_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        device = self._load(device_id)
        if device is None or not device.belongs_to(user_id):
            return False
        self._remove(device_id)
        return True

    def delete_by_token(self, platform: DevicePlatform, token: str) -> bool:
        device_id = self._tokens.get(self._key(platform, token))
        if device_id is None:
            return False
        self._remove(device_id)
        return True

    def _load(self, device_id: uuid.UUID) -> DeviceToken | None:
        raw = self._records.get(device_id)
        return None if raw is None else device_token_codec.decode(raw)

    def _remove(self, device_id: uuid.UUID) -> None:
        raw = self._records.pop(device_id, None)
        if raw is None:
            return
        device = device_token_codec.decode(raw)
        self._tokens.pop(self._key(device.platform, device.token), None)
        owned = self._users.get(device.user_id)
        if owned is not None:
            owned.discard(device_id)
            if not owned:
                self._users.pop(device.user_id, None)
