"""NTF-302: the device registry, proven against both adapters.

Every test runs against the in-memory store and a live Redis. The property that matters most
is the one a single adapter would hide: a token belongs to exactly one account. A device that
signs out and signs in as somebody else must move, not duplicate -- a duplicate means the
previous owner's notifications keep arriving on that phone.

The Redis-specific tests also pin the absence of a TTL. Registrations are removed explicitly,
never on a timer, for the same reason preferences are: a device that stops receiving push at
an arbitrary moment is indistinguishable, to the user, from the app being broken.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from app.adapters.keys import NotificationKeys
from app.adapters.redis_device_token_repository import RedisDeviceTokenRepository
from app.domain.device_token import DeviceToken
from app.domain.enums import DevicePlatform
from tests.conftest import drop_namespace, isolated_namespace

USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
TOKEN = "fcm-token-abc123"


def _device(
    *,
    user_id: uuid.UUID = USER,
    platform: DevicePlatform = DevicePlatform.ANDROID,
    token: str = TOKEN,
    now: datetime = NOW,
) -> DeviceToken:
    return DeviceToken.register(user_id, platform, token, now=now)


# -- the port contract, both adapters ---------------------------------------------------


def test_an_unknown_token_reads_as_absent(device_repository):
    assert device_repository.find_by_token(DevicePlatform.ANDROID, TOKEN) is None


def test_saving_then_reading_by_token_returns_an_equal_record(device_repository):
    device = _device()

    device_repository.upsert(device)

    assert device_repository.find_by_token(device.platform, device.token) == device


def test_lookup_normalizes_the_token_it_is_given(device_repository):
    device = _device()
    device_repository.upsert(device)

    assert device_repository.find_by_token(device.platform, f"  {TOKEN}\n") == device


def test_a_registration_is_owner_scoped(device_repository):
    device = _device()
    device_repository.upsert(device)

    assert device_repository.get(device.id, user_id=USER) == device
    assert device_repository.get(device.id, user_id=OTHER_USER) is None


def test_an_unknown_id_reads_as_absent(device_repository):
    assert device_repository.get(uuid.uuid4(), user_id=USER) is None


def test_listing_returns_every_device_for_one_user_newest_first(device_repository):
    older = _device(token="older", now=NOW)
    newer = _device(token="newer", now=NOW + timedelta(minutes=1))
    device_repository.upsert(older)
    device_repository.upsert(newer)

    assert device_repository.list_for_user(USER) == [newer, older]
    assert device_repository.list_for_user(OTHER_USER) == []


def test_two_platforms_with_the_same_token_are_distinct_registrations(device_repository):
    """The same string from FCM and APNs is two addresses, not one."""
    android = _device(platform=DevicePlatform.ANDROID)
    ios = _device(platform=DevicePlatform.IOS, now=NOW + timedelta(minutes=1))
    device_repository.upsert(android)
    device_repository.upsert(ios)

    assert device_repository.find_by_token(DevicePlatform.ANDROID, TOKEN) == android
    assert device_repository.find_by_token(DevicePlatform.IOS, TOKEN) == ios
    assert len(device_repository.list_for_user(USER)) == 2


def test_refreshing_the_same_token_replaces_the_record_rather_than_adding_one(
    device_repository,
):
    device = _device()
    device_repository.upsert(device)

    refreshed = device.refreshed(now=NOW + timedelta(hours=1))
    device_repository.upsert(refreshed)

    assert device_repository.find_by_token(device.platform, device.token) == refreshed
    assert device_repository.list_for_user(USER) == [refreshed]


def test_a_token_that_changes_accounts_moves_and_does_not_duplicate(device_repository):
    device = _device()
    device_repository.upsert(device)

    moved = device.reassigned_to(OTHER_USER, now=NOW + timedelta(minutes=5))
    device_repository.upsert(moved)

    assert device_repository.find_by_token(device.platform, device.token) == moved
    assert device_repository.list_for_user(USER) == []
    assert device_repository.list_for_user(OTHER_USER) == [moved]
    assert device_repository.get(device.id, user_id=USER) is None


def test_revoking_a_device_is_owner_scoped(device_repository):
    device = _device()
    device_repository.upsert(device)

    assert device_repository.delete(device.id, user_id=OTHER_USER) is False
    assert device_repository.find_by_token(device.platform, device.token) == device

    assert device_repository.delete(device.id, user_id=USER) is True
    assert device_repository.find_by_token(device.platform, device.token) is None
    assert device_repository.list_for_user(USER) == []


def test_provider_feedback_removes_a_token_without_an_owner(device_repository):
    device = _device()
    device_repository.upsert(device)

    assert device_repository.delete_by_token(device.platform, device.token) is True
    assert device_repository.get(device.id, user_id=USER) is None
    assert device_repository.delete_by_token(device.platform, device.token) is False


def test_deleting_a_token_does_not_touch_the_same_string_on_the_other_platform(
    device_repository,
):
    android = _device(platform=DevicePlatform.ANDROID)
    ios = _device(platform=DevicePlatform.IOS, now=NOW + timedelta(minutes=1))
    device_repository.upsert(android)
    device_repository.upsert(ios)

    device_repository.delete_by_token(DevicePlatform.ANDROID, TOKEN)

    assert device_repository.find_by_token(DevicePlatform.ANDROID, TOKEN) is None
    assert device_repository.find_by_token(DevicePlatform.IOS, TOKEN) == ios


def test_registrations_of_different_users_are_independent(device_repository):
    first = _device(user_id=USER, token="first")
    second = _device(user_id=OTHER_USER, token="second")
    device_repository.upsert(first)
    device_repository.upsert(second)

    assert device_repository.list_for_user(USER) == [first]
    assert device_repository.list_for_user(OTHER_USER) == [second]


# -- Redis specifics --------------------------------------------------------------------

TOKEN_HASH = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()


def _redis_repository(redis_client, namespace: str) -> RedisDeviceTokenRepository:
    return RedisDeviceTokenRepository(
        redis_client,  # type: ignore[arg-type]
        keys=NotificationKeys(namespace=namespace),
    )


def test_a_registration_is_stored_without_an_expiry(redis_client):
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = _redis_repository(redis_client, namespace)
    device = _device()

    try:
        repository.upsert(device)

        assert redis_client.ttl(keys.device(device.id)) == -1
        assert redis_client.ttl(keys.user_devices(USER)) == -1
    finally:
        drop_namespace(redis_client, namespace)


def test_the_token_index_does_not_expose_the_raw_token(redis_client):
    """The address is stored in the record -- never in a key an operator might print."""
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = _redis_repository(redis_client, namespace)
    device = _device()

    try:
        repository.upsert(device)

        index_key = keys.device_token_index("android", TOKEN_HASH)
        assert redis_client.exists(index_key) == 1
        assert TOKEN not in index_key
        assert redis_client.get(index_key) == str(device.id)
    finally:
        drop_namespace(redis_client, namespace)


def test_device_keys_are_namespaced_and_versioned(redis_client):
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = _redis_repository(redis_client, namespace)
    device = _device()

    try:
        repository.upsert(device)

        assert keys.device(device.id).startswith(f"{namespace}:")
        assert keys.user_devices(USER).startswith(f"{namespace}:")
        assert redis_client.exists(keys.device(device.id)) == 1
    finally:
        drop_namespace(redis_client, namespace)


def test_a_dangling_token_index_is_dropped_on_read(redis_client):
    """A half-written registration must not make the token look permanently taken."""
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = _redis_repository(redis_client, namespace)
    device = _device()

    try:
        repository.upsert(device)
        redis_client.delete(keys.device(device.id))

        assert repository.find_by_token(device.platform, device.token) is None
        assert redis_client.exists(keys.device_token_index("android", TOKEN_HASH)) == 0
    finally:
        drop_namespace(redis_client, namespace)
