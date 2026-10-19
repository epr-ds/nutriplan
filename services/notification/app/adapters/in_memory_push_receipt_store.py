"""The in-process push-receipt store -- the dev/CI twin of the Redis one (NTF-305).

Records are kept as **encoded JSON**, as in the other in-memory adapters, so the codec runs on
the dev path too and a value that could not survive a round-trip fails locally rather than only
against Redis. The TTL is honoured against a monotonic clock so a test can prove a receipt
disappears with its notification without waiting a month.

Not safe across processes, which is the point of it being the fallback rather than the default:
two replicas each fanning out with their own receipts would send a second push to every device.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.adapters import push_receipt_codec
from app.domain.push_receipt import PushReceipt


@dataclass(slots=True)
class _Entry:
    record: str
    expires_at: float


class InMemoryPushReceiptStore:
    """A dict-backed :class:`~app.domain.repositories.PushReceiptStore`."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 2_592_000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._clock = clock or time.monotonic
        self._buckets: dict[uuid.UUID, dict[uuid.UUID, _Entry]] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        """How long a receipt survives without the notification being re-recorded."""
        return self._ttl_seconds

    def _live(self, notification_id: uuid.UUID) -> dict[uuid.UUID, _Entry]:
        """Return the live bucket for a notification, dropping it once every entry aged out."""
        bucket = self._buckets.get(notification_id)
        if bucket is None:
            return {}
        now = self._clock()
        expired = [device_id for device_id, entry in bucket.items() if entry.expires_at <= now]
        for device_id in expired:
            del bucket[device_id]
        if not bucket:
            self._buckets.pop(notification_id, None)
            return {}
        return bucket

    def record(self, receipt: PushReceipt) -> PushReceipt:
        with self._lock:
            bucket = self._live(receipt.notification_id)
            bucket[receipt.device_id] = _Entry(
                record=push_receipt_codec.encode(receipt),
                expires_at=self._clock() + self._ttl_seconds,
            )
            self._buckets[receipt.notification_id] = bucket
        return receipt

    def get(self, notification_id: uuid.UUID, device_id: uuid.UUID) -> PushReceipt | None:
        with self._lock:
            entry = self._live(notification_id).get(device_id)
        return None if entry is None else push_receipt_codec.decode(entry.record)

    def list_for(self, notification_id: uuid.UUID) -> list[PushReceipt]:
        with self._lock:
            records = [entry.record for entry in self._live(notification_id).values()]
        receipts = [push_receipt_codec.decode(record) for record in records]
        return sorted(
            receipts,
            key=lambda receipt: (receipt.updated_at, str(receipt.device_id)),
            reverse=True,
        )
