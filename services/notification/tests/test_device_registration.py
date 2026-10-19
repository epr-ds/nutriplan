"""NTF-302: the registration use cases.

Uses the real in-memory adapter -- the store's own contract is proven against Redis in
``test_device_token_store.py`` -- so these tests are about the *decisions* this layer makes:
is this a new device, a refresh, or a change of owner? Those decisions are the part a client
depends on, and each has a distinct observable outcome.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.in_memory_device_token_repository import InMemoryDeviceTokenRepository
from app.application.devices import DeviceRegistrationService
from app.domain.enums import DevicePlatform
from app.domain.errors import DeviceTokenNotFound

USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
TOKEN = "fcm-token-abc123"
ANDROID = DevicePlatform.ANDROID


@pytest.fixture
def service() -> DeviceRegistrationService:
    return DeviceRegistrationService(InMemoryDeviceTokenRepository())


def test_a_first_registration_creates_a_device(service):
    device = service.register(USER, ANDROID, TOKEN, now=NOW)

    assert device.user_id == USER
    assert device.platform is ANDROID
    assert device.token == TOKEN
    assert service.list_devices(USER) == (device,)


def test_registering_the_same_token_again_is_a_refresh_not_a_second_device(service):
    first = service.register(USER, ANDROID, TOKEN, now=NOW)

    refreshed = service.register(USER, ANDROID, TOKEN, now=NOW + timedelta(hours=1))

    assert refreshed.id == first.id
    assert refreshed.created_at == first.created_at
    assert refreshed.updated_at == NOW + timedelta(hours=1)
    assert len(service.list_devices(USER)) == 1


def test_a_token_that_changes_accounts_moves_to_the_new_owner(service):
    first = service.register(USER, ANDROID, TOKEN, now=NOW)

    moved = service.register(OTHER_USER, ANDROID, TOKEN, now=NOW + timedelta(minutes=5))

    assert moved.id == first.id
    assert moved.user_id == OTHER_USER
    assert service.list_devices(USER) == ()
    assert service.list_devices(OTHER_USER) == (moved,)


def test_two_devices_for_one_user_are_both_listed(service):
    phone = service.register(USER, ANDROID, "phone", now=NOW)
    tablet = service.register(USER, DevicePlatform.IOS, "tablet", now=NOW + timedelta(minutes=1))

    assert service.list_devices(USER) == (tablet, phone)


def test_revoking_an_owned_device_removes_it(service):
    device = service.register(USER, ANDROID, TOKEN, now=NOW)

    service.revoke(USER, device.id)

    assert service.list_devices(USER) == ()


def test_revoking_another_users_device_is_not_found(service):
    device = service.register(USER, ANDROID, TOKEN, now=NOW)

    with pytest.raises(DeviceTokenNotFound):
        service.revoke(OTHER_USER, device.id)

    assert service.list_devices(USER) == (device,)


def test_revoking_an_unknown_device_is_not_found(service):
    with pytest.raises(DeviceTokenNotFound):
        service.revoke(USER, uuid.uuid4())


def test_pruning_a_dead_token_removes_it_regardless_of_owner(service):
    service.register(USER, ANDROID, TOKEN, now=NOW)

    assert service.prune(ANDROID, TOKEN) is True
    assert service.list_devices(USER) == ()
    assert service.prune(ANDROID, TOKEN) is False


def test_pruning_one_platform_leaves_the_other_alone(service):
    service.register(USER, ANDROID, TOKEN, now=NOW)
    ios = service.register(USER, DevicePlatform.IOS, TOKEN, now=NOW + timedelta(minutes=1))

    service.prune(ANDROID, TOKEN)

    assert service.list_devices(USER) == (ios,)
