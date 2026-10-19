"""The Redis-backed push-receipt store (NTF-305).

One key per notification, a hash of device id to receipt::

    {ns}:v1:pr:{notification_id}   -> { device_id: receipt JSON }   (hash, EX retention)

A hash rather than a key per (notification, device) because every question this store answers
is about one notification -- "which devices has it reached, and re-running the fan-out must not
send twice" -- and because the whole bucket can then be given one TTL, expiring with the
notification it describes.

Unlike device registrations, receipts **do** carry a TTL. A registration is an address that
stays valid until revoked; a receipt is news about one message, and news that outlives the
notification it belongs to is both useless and a small privacy leak.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from app.adapters import push_receipt_codec
from app.adapters.keys import NotificationKeys
from app.domain.push_receipt import PushReceipt


class RedisLike(Protocol):
    """The slice of the redis-py client this adapter relies on."""

    def hset(self, name: str, key: str, value: str) -> Any: ...
    def hget(self, name: str, key: str) -> Any: ...
    def hgetall(self, name: str) -> dict[Any, Any]: ...
    def expire(self, name: str, time: int) -> Any: ...


class RedisPushReceiptStore:
    """Adapt a redis-py-style client to the push-receipt persistence port."""

    def __init__(
        self,
        client: RedisLike,
        *,
        keys: NotificationKeys | None = None,
        ttl_seconds: int = 2_592_000,
    ) -> None:
        self._client = client
        self._keys = keys or NotificationKeys()
        self._ttl_seconds = max(1, int(ttl_seconds))

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        keys: NotificationKeys | None = None,
        ttl_seconds: int = 2_592_000,
    ) -> RedisPushReceiptStore:
        """Build a store from a ``redis://`` URL, importing the driver lazily."""
        import redis  # imported here so the package never hard-depends on a running Redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client, keys=keys, ttl_seconds=ttl_seconds)

    @staticmethod
    def _text(value: Any) -> str | None:
        """Normalize a redis-py reply to ``str`` whether or not decoding is enabled."""
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    def record(self, receipt: PushReceipt) -> PushReceipt:
        key = self._keys.push_receipts(receipt.notification_id)
        self._client.hset(key, str(receipt.device_id), push_receipt_codec.encode(receipt))
        # Refresh the bucket's lifetime on every write: the clock that matters is the last
        # time this notification was touched, not the first device that happened to answer.
        self._client.expire(key, self._ttl_seconds)
        return receipt

    def get(self, notification_id: uuid.UUID, device_id: uuid.UUID) -> PushReceipt | None:
        raw = self._text(
            self._client.hget(self._keys.push_receipts(notification_id), str(device_id))
        )
        return None if raw is None else push_receipt_codec.decode(raw)

    def list_for(self, notification_id: uuid.UUID) -> list[PushReceipt]:
        raw = self._client.hgetall(self._keys.push_receipts(notification_id))
        receipts = [push_receipt_codec.decode(self._text(value) or "") for value in raw.values()]
        return sorted(
            receipts,
            key=lambda receipt: (receipt.updated_at, str(receipt.device_id)),
            reverse=True,
        )
