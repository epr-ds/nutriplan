"""NTF-302: the device-token domain model.

The interesting behaviour is the lifecycle, not the fields: a re-registration must be a
refresh of the *same* record, and a token arriving under a new account must move rather than
duplicate. Both are asserted here before any store or HTTP layer is involved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.device_token import MAX_TOKEN_LENGTH, DeviceToken
from app.domain.enums import DevicePlatform
from app.domain.errors import InvalidDeviceToken

USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()
TOKEN = "fcm-token-abc123"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _registered(*, now: datetime = NOW) -> DeviceToken:
    return DeviceToken.register(USER, DevicePlatform.ANDROID, TOKEN, now=now)


def test_register_mints_an_id_and_stamps_both_timestamps():
    device = _registered()

    assert device.id is not None
    assert device.user_id == USER
    assert device.platform is DevicePlatform.ANDROID
    assert device.token == TOKEN
    assert device.created_at == NOW
    assert device.updated_at == NOW


def test_register_normalizes_the_platform_from_its_wire_value():
    device = DeviceToken.register(USER, "ios", TOKEN, now=NOW)  # type: ignore[arg-type]

    assert device.platform is DevicePlatform.IOS


def test_register_strips_a_token_padded_by_the_client():
    device = DeviceToken.register(USER, DevicePlatform.ANDROID, f"  {TOKEN}\n", now=NOW)

    assert device.token == TOKEN


@pytest.mark.parametrize(
    "token",
    [
        "",
        "   ",
        "has space",
        "line\nbreak",
        "x" * (MAX_TOKEN_LENGTH + 1),
    ],
)
def test_an_unusable_token_is_refused(token):
    with pytest.raises(InvalidDeviceToken):
        DeviceToken.register(USER, DevicePlatform.ANDROID, token, now=NOW)


def test_a_non_string_token_is_refused():
    with pytest.raises(InvalidDeviceToken):
        DeviceToken.register(USER, DevicePlatform.ANDROID, 123, now=NOW)  # type: ignore[arg-type]


def test_an_unknown_platform_is_refused():
    with pytest.raises(InvalidDeviceToken):
        DeviceToken.register(USER, "windows", TOKEN, now=NOW)  # type: ignore[arg-type]


def test_a_naive_timestamp_is_refused():
    with pytest.raises(InvalidDeviceToken):
        DeviceToken.register(USER, DevicePlatform.ANDROID, TOKEN, now=datetime(2026, 10, 18))


def test_a_record_stamped_before_its_creation_is_refused():
    with pytest.raises(InvalidDeviceToken):
        DeviceToken(
            id=uuid.uuid4(),
            user_id=USER,
            platform=DevicePlatform.ANDROID,
            token=TOKEN,
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )


# -- refresh ----------------------------------------------------------------------------


def test_refresh_keeps_the_identity_and_moves_only_updated_at():
    device = _registered()
    later = NOW + timedelta(hours=2)

    refreshed = device.refreshed(now=later)

    assert refreshed.id == device.id
    assert refreshed.created_at == device.created_at
    assert refreshed.token == device.token
    assert refreshed.user_id == device.user_id
    assert refreshed.updated_at == later


def test_refresh_never_moves_updated_at_backwards():
    """A replica with a slow clock must not make a recently active device look older."""
    device = _registered()
    earlier = NOW - timedelta(hours=1)

    assert device.refreshed(now=earlier).updated_at == device.updated_at


def test_refresh_rejects_a_naive_timestamp():
    with pytest.raises(InvalidDeviceToken):
        _registered().refreshed(now=datetime(2026, 10, 18))


# -- reassignment -----------------------------------------------------------------------


def test_reassignment_moves_ownership_and_keeps_the_record_identity():
    device = _registered()
    later = NOW + timedelta(minutes=5)

    moved = device.reassigned_to(OTHER_USER, now=later)

    assert moved.id == device.id
    assert moved.created_at == device.created_at
    assert moved.user_id == OTHER_USER
    assert moved.updated_at == later
    assert moved.belongs_to(OTHER_USER) is True
    assert moved.belongs_to(USER) is False


def test_reassignment_never_moves_updated_at_backwards():
    device = _registered()

    assert device.reassigned_to(OTHER_USER, now=NOW - timedelta(seconds=1)).updated_at == NOW
