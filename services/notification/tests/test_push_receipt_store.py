"""NTF-305: per-device push receipts, proven against both adapters.

Every test runs against the in-memory store and a live Redis. The property that matters is the
one the fan-out depends on: a receipt already on record means that device must not be sent a
second push when a partially completed fan-out is resumed. An in-memory stand-in that forgot a
receipt would let CI pass while production double-nudged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.in_memory_push_receipt_store import InMemoryPushReceiptStore
from app.adapters.keys import NotificationKeys
from app.adapters.redis_push_receipt_store import RedisPushReceiptStore
from app.domain.enums import DeliveryStatus, DevicePlatform
from app.domain.errors import InvalidPushReceipt
from app.domain.push_receipt import PushReceipt
from tests.conftest import drop_namespace, isolated_namespace

NOTIFICATION = uuid.uuid4()
OTHER_NOTIFICATION = uuid.uuid4()
DEVICE = uuid.uuid4()
OTHER_DEVICE = uuid.uuid4()
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _accepted(
    *,
    notification_id: uuid.UUID = NOTIFICATION,
    device_id: uuid.UUID = DEVICE,
    now: datetime = NOW,
    message_id: str | None = "message-1",
) -> PushReceipt:
    return PushReceipt.accepted_by(
        notification_id,
        device_id,
        DevicePlatform.ANDROID,
        message_id=message_id,
        now=now,
    )


def _refused(
    *,
    notification_id: uuid.UUID = NOTIFICATION,
    device_id: uuid.UUID = DEVICE,
    now: datetime = NOW,
) -> PushReceipt:
    return PushReceipt.refused_by(
        notification_id,
        device_id,
        DevicePlatform.IOS,
        error="BadDeviceToken",
        pruned=True,
        now=now,
    )


# -- the port contract, both adapters ---------------------------------------------------


def test_an_unknown_receipt_reads_as_absent(push_receipt_store):
    assert push_receipt_store.get(NOTIFICATION, DEVICE) is None


def test_recording_then_reading_returns_an_equal_receipt(push_receipt_store):
    receipt = _accepted()

    push_receipt_store.record(receipt)

    assert push_receipt_store.get(NOTIFICATION, DEVICE) == receipt


def test_listing_returns_one_receipt_per_device(push_receipt_store):
    push_receipt_store.record(_accepted())

    assert push_receipt_store.list_for(NOTIFICATION) == [_accepted()]


def test_receipts_of_different_notifications_are_independent(push_receipt_store):
    push_receipt_store.record(_accepted())
    push_receipt_store.record(_accepted(notification_id=OTHER_NOTIFICATION))

    assert push_receipt_store.list_for(NOTIFICATION) == [_accepted()]
    assert push_receipt_store.list_for(OTHER_NOTIFICATION) == [
        _accepted(notification_id=OTHER_NOTIFICATION)
    ]


def test_recording_the_same_device_again_overwrites_rather_than_duplicates(push_receipt_store):
    push_receipt_store.record(_refused())

    push_receipt_store.record(_accepted())

    assert push_receipt_store.list_for(NOTIFICATION) == [_accepted()]


def test_a_refusal_keeps_its_error_and_pruned_flag(push_receipt_store):
    push_receipt_store.record(_refused())

    stored = push_receipt_store.get(NOTIFICATION, DEVICE)

    assert stored is not None
    assert stored.status is DeliveryStatus.FAILED
    assert stored.error == "BadDeviceToken"
    assert stored.pruned is True


def test_listing_is_most_recently_updated_first(push_receipt_store):
    older = _accepted(device_id=DEVICE, now=NOW)
    newer = _accepted(device_id=OTHER_DEVICE, now=NOW + timedelta(minutes=1))
    push_receipt_store.record(older)
    push_receipt_store.record(newer)

    assert push_receipt_store.list_for(NOTIFICATION) == [newer, older]


# -- the domain object ------------------------------------------------------------------


@pytest.mark.parametrize("status", [DeliveryStatus.PENDING, DeliveryStatus.SUPPRESSED])
def test_a_receipt_refuses_a_non_terminal_status(status):
    with pytest.raises(InvalidPushReceipt):
        PushReceipt(
            notification_id=NOTIFICATION,
            device_id=DEVICE,
            platform=DevicePlatform.ANDROID,
            status=status,
            updated_at=NOW,
        )


def test_a_receipt_requires_an_aware_timestamp():
    with pytest.raises(InvalidPushReceipt):
        _accepted(now=datetime(2026, 10, 18, 12, 0))


# -- adapter-specific behaviour ---------------------------------------------------------


def test_an_in_memory_receipt_expires_with_its_notification():
    now = [1_000.0]
    store = InMemoryPushReceiptStore(ttl_seconds=60, clock=lambda: now[0])
    store.record(_accepted())

    now[0] += 61

    assert store.get(NOTIFICATION, DEVICE) is None
    assert store.list_for(NOTIFICATION) == []


def _redis_store(redis_client, namespace: str) -> RedisPushReceiptStore:
    return RedisPushReceiptStore(
        redis_client,  # type: ignore[arg-type]
        keys=NotificationKeys(namespace=namespace),
        ttl_seconds=3_600,
    )


def test_a_redis_receipt_is_a_namespaced_hash_with_an_expiry(redis_client):
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = _redis_store(redis_client, namespace)

    try:
        store.record(_accepted())
        store.record(_accepted(device_id=OTHER_DEVICE))

        key = keys.push_receipts(NOTIFICATION)
        assert key == f"{namespace}:v1:pr:{NOTIFICATION}"
        assert redis_client.type(key) == "hash"
        assert sorted(redis_client.hkeys(key)) == sorted([str(DEVICE), str(OTHER_DEVICE)])
        assert 0 < redis_client.ttl(key) <= 3_600
    finally:
        drop_namespace(redis_client, namespace)


def test_a_missing_redis_receipt_does_not_create_the_bucket(redis_client):
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = _redis_store(redis_client, namespace)

    try:
        assert store.get(NOTIFICATION, DEVICE) is None

        assert redis_client.exists(keys.push_receipts(NOTIFICATION)) == 0
    finally:
        drop_namespace(redis_client, namespace)
