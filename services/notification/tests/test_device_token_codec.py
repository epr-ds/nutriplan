"""NTF-302: the stored form of a device registration.

The codec is the contract between the two adapters and between the store and the API. Its
two jobs are worth pinning separately: the round-trip must preserve identity, and a corrupt
record must fail loudly rather than decode into a registration that addresses nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.adapters import device_token_codec
from app.domain.device_token import DeviceToken
from app.domain.enums import DevicePlatform
from app.domain.errors import InvalidDeviceToken

USER = uuid.uuid4()
NOW = datetime(2026, 10, 18, 12, 30, tzinfo=UTC)


def _device() -> DeviceToken:
    return DeviceToken.register(USER, DevicePlatform.IOS, "apns-token-123", now=NOW)


def test_the_codec_round_trips_a_registration():
    device = _device()

    assert device_token_codec.decode(device_token_codec.encode(device)) == device


def test_the_stored_form_is_camel_case_json():
    device = _device()
    encoded = json.loads(device_token_codec.encode(device))

    assert encoded == {
        "id": str(device.id),
        "userId": str(USER),
        "platform": "ios",
        "token": "apns-token-123",
        "createdAt": NOW.isoformat(),
        "updatedAt": NOW.isoformat(),
    }


def test_the_token_is_stored_in_full():
    """A digest cannot be pushed to; the delivery path needs the address itself."""
    assert json.loads(device_token_codec.encode(_device()))["token"] == "apns-token-123"


def test_decoding_accepts_a_platform_enum_in_the_record():
    record = device_token_codec.to_record(_device())
    record["platform"] = DevicePlatform.IOS

    assert device_token_codec.from_record(record).platform is DevicePlatform.IOS


@pytest.mark.parametrize(
    "record",
    [
        {"id": "not-a-uuid"},
        {"platform": "windows"},
        {"token": ""},
        {"createdAt": "not-a-time"},
        {"updatedAt": "2026-10-18T12:00:00"},
    ],
)
def test_a_corrupt_field_is_a_domain_error(record):
    base = device_token_codec.to_record(_device())
    base.update(record)

    with pytest.raises(InvalidDeviceToken):
        device_token_codec.from_record(base)


def test_an_empty_record_is_a_domain_error():
    with pytest.raises(InvalidDeviceToken):
        device_token_codec.from_record({})


def test_non_json_is_a_domain_error():
    with pytest.raises(InvalidDeviceToken):
        device_token_codec.decode("{not json")


def test_a_non_object_record_is_a_domain_error():
    with pytest.raises(InvalidDeviceToken):
        device_token_codec.decode("[]")
