"""The Redis-backed device-token store (NTF-302).

Three keys per registration, all sharing the service namespace and schema version::

    {ns}:v1:dt:{device_id}                 -> the JSON record
    {ns}:v1:dtx:{platform}:{sha256(token)} -> the id owning that token
    {ns}:v1:u:{user_id}:devices            -> every id for the user (sorted set by created_at)

The token index is what enforces "one token, one account". Registration looks the token up
before writing, so a device that signed in as somebody else is *moved* rather than duplicated;
duplicating it would deliver the previous owner's notifications to the new owner's phone.

The token is hashed into the index key but stored in full in the record. Hashing the key keeps
a provider address out of ``redis-cli`` output and key-pattern scans, while the record still
holds the address the delivery path needs -- a digest cannot be pushed to.

**Nothing here carries a TTL.** A registration is not news that goes stale; it is an address
that stays valid until the client revokes it or the provider reports it dead. Expiring it on a
timer would cut off push at a moment unrelated to anything the user did, so removal is always
explicit (:meth:`delete`, :meth:`delete_by_token`).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from typing import Any, Protocol

from app.adapters import device_token_codec
from app.adapters.keys import NotificationKeys
from app.domain.device_token import DeviceToken, normalize_token
from app.domain.enums import DevicePlatform


def _token_hash(token: str) -> str:
    """A stable, opaque key component for a provider token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str) -> Any: ...
    def delete(self, *keys: str) -> Any: ...
    def zadd(self, key: str, mapping: dict[str, float]) -> Any: ...
    def zrem(self, key: str, *members: str) -> Any: ...
    def zrevrange(self, key: str, start: int, end: int) -> list[Any]: ...
    def mget(self, keys: Iterable[str]) -> list[Any]: ...


class RedisDeviceTokenRepository:
    """Adapt a redis-py-style client to the device-token persistence port."""

    def __init__(self, client: RedisLike, *, keys: NotificationKeys | None = None) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()

    @classmethod
    def from_url(
        cls, url: str, *, keys: NotificationKeys | None = None
    ) -> RedisDeviceTokenRepository:
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

    def _token_key(self, platform: DevicePlatform, token: str) -> str:
        return self._keys.device_token_index(
            DevicePlatform(platform).value, _token_hash(normalize_token(token))
        )

    def _load(self, device_id: uuid.UUID) -> DeviceToken | None:
        raw = self._text(self._client.get(self._keys.device(device_id)))
        return None if raw is None else device_token_codec.decode(raw)

    def _remove(self, device_id: uuid.UUID) -> bool:
        device = self._load(device_id)
        if device is None:
            return False
        self._client.delete(self._keys.device(device_id))
        self._client.delete(self._token_key(device.platform, device.token))
        self._client.zrem(self._keys.user_devices(device.user_id), str(device_id))
        return True

    def find_by_token(self, platform: DevicePlatform, token: str) -> DeviceToken | None:
        index_key = self._token_key(platform, token)
        raw_id = self._text(self._client.get(index_key))
        if raw_id is None:
            return None
        try:
            device_id = uuid.UUID(raw_id)
        except ValueError:
            self._client.delete(index_key)
            return None
        device = self._load(device_id)
        if device is None:
            # The index outlived its record (a partial write, or a manual delete). Drop the
            # dangling pointer only if it still names the id we just failed to load.
            if self._text(self._client.get(index_key)) == raw_id:
                self._client.delete(index_key)
            return None
        return device

    def get(self, device_id: uuid.UUID, *, user_id: uuid.UUID) -> DeviceToken | None:
        device = self._load(device_id)
        if device is None or not device.belongs_to(user_id):
            return None
        return device

    def list_for_user(self, user_id: uuid.UUID) -> list[DeviceToken]:
        index_key = self._keys.user_devices(user_id)
        ids = [self._text(entry) for entry in self._client.zrevrange(index_key, 0, -1)]
        present = [device_id for device_id in ids if device_id is not None]
        if not present:
            return []

        records = self._client.mget([self._keys.device(device_id) for device_id in present])
        devices: list[DeviceToken] = []
        stale: list[str] = []
        for device_id, raw in zip(present, records, strict=True):
            text = self._text(raw)
            if text is None:
                stale.append(device_id)
                continue
            devices.append(device_token_codec.decode(text))

        if stale:
            self._client.zrem(index_key, *stale)
        return [device for device in devices if device.belongs_to(user_id)]

    def upsert(self, device: DeviceToken) -> DeviceToken:
        token_key = self._token_key(device.platform, device.token)
        previous_id = self._text(self._client.get(token_key))
        if previous_id is not None and previous_id != str(device.id):
            try:
                previous_uuid = uuid.UUID(previous_id)
            except ValueError:
                self._client.delete(token_key)
            else:
                self._remove(previous_uuid)

        stored = self._load(device.id)
        if stored is not None:
            if (stored.platform, stored.token) != (device.platform, device.token):
                self._client.delete(self._token_key(stored.platform, stored.token))
            if stored.user_id != device.user_id:
                self._client.zrem(self._keys.user_devices(stored.user_id), str(device.id))

        self._client.set(self._keys.device(device.id), device_token_codec.encode(device))
        self._client.set(token_key, str(device.id))
        self._client.zadd(
            self._keys.user_devices(device.user_id),
            {str(device.id): device.created_at.timestamp()},
        )
        return device

    def delete(self, device_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        device = self._load(device_id)
        if device is None or not device.belongs_to(user_id):
            return False
        return self._remove(device_id)

    def delete_by_token(self, platform: DevicePlatform, token: str) -> bool:
        token_key = self._token_key(platform, token)
        previous_id = self._text(self._client.get(token_key))
        if previous_id is None:
            return False
        try:
            device_id = uuid.UUID(previous_id)
        except ValueError:
            self._client.delete(token_key)
            return False
        if not self._remove(device_id):
            # The record is already gone; drop the dangling pointer so the token is free.
            self._client.delete(token_key)
            return False
        return True
