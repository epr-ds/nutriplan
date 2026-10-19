"""NTF-302: the device endpoints conform to ``contracts/notification.openapi.yaml``.

The two-way path gate lives in ``test_feed_contract.py`` and now covers these routes too.
What is added here is the shape: the schemas, the platform enum, the idempotent status
codes, and the handful of details a generated client would otherwise get wrong.

The one that matters most is that the request has no ``userId``. The owner comes from the
token, and a ``userId`` field would be the whole bug -- a caller registering a device against
somebody else's account.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.api.schemas import RegisterDeviceRequest, RegisteredDeviceResponse
from app.domain.device_token import MAX_TOKEN_LENGTH
from app.domain.enums import DevicePlatform
from app.main import app

PATH = "/notifications/devices"
DOCUMENTED_DELETE_PATH = "/notifications/devices/{deviceId}"


def _schema() -> dict:
    return app.openapi()


def _aliases(model: type) -> set[str]:
    return {field.alias or name for name, field in model.model_fields.items()}


def _locate_spec() -> Path | None:
    override = os.environ.get("NOTIFICATION_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "notification.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _spec() -> dict:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("notification.openapi.yaml not found under CI")
        pytest.skip("notification.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def _schemas() -> dict:
    return _spec()["components"]["schemas"]


# -- the implementation, on its own ----------------------------------------------------


def test_the_device_operations_are_published():
    published = _schema()["paths"]
    assert {"post"} <= set(published[PATH])
    assert {"delete"} <= set(published["/notifications/devices/{device_id}"])


def test_the_device_operations_carry_stable_operation_ids():
    published = _schema()["paths"]
    assert published[PATH]["post"]["operationId"].startswith("register_device")
    assert published["/notifications/devices/{device_id}"]["delete"]["operationId"].startswith(
        "revoke_device"
    )


def test_the_owner_comes_from_the_token_not_the_request():
    """A ``userId`` parameter or body field would let a caller register someone else's device."""
    request_fields = _aliases(RegisterDeviceRequest)
    assert "userId" not in request_fields
    assert _schema()["paths"][PATH]["post"].get("parameters", []) == []


def test_registration_is_201_and_revocation_is_204():
    published = _schema()["paths"]
    assert "201" in published[PATH]["post"]["responses"]
    assert "204" in published["/notifications/devices/{device_id}"]["delete"]["responses"]


# -- the implementation against the contract -------------------------------------------


def test_both_operations_are_documented():
    documented = _spec()["paths"]
    assert PATH in documented
    assert DOCUMENTED_DELETE_PATH in documented


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("RegisterDevice", RegisterDeviceRequest),
        ("RegisteredDevice", RegisteredDeviceResponse),
    ],
)
def test_the_documented_schema_matches_the_model(name, model):
    assert _aliases(model) == set(_schemas()[name]["properties"])


def test_the_documented_platform_enum_matches_the_domain():
    documented = set(_schemas()["DevicePlatform"]["enum"])
    assert documented == {platform.value for platform in DevicePlatform}


def test_platform_is_documented_as_a_shared_enum():
    assert _schemas()["RegisterDevice"]["properties"]["platform"] == {
        "$ref": "#/components/schemas/DevicePlatform"
    }


def test_both_registration_fields_are_required():
    assert set(_schemas()["RegisterDevice"]["required"]) == {"platform", "token"}


def test_the_documented_token_bounds_match_the_domain():
    token = _schemas()["RegisterDevice"]["properties"]["token"]
    assert token["minLength"] == 1
    assert token["maxLength"] == MAX_TOKEN_LENGTH


def test_the_registered_device_requires_its_identity_and_timestamps():
    assert set(_schemas()["RegisteredDevice"]["required"]) == {
        "id",
        "platform",
        "createdAt",
        "updatedAt",
    }


def test_the_registered_device_does_not_document_the_token():
    """The API never returns it; documenting it would invite clients to rely on it."""
    assert "token" not in _schemas()["RegisteredDevice"]["properties"]


def test_the_delete_parameter_is_a_required_uuid_in_the_path():
    parameter = _spec()["paths"][DOCUMENTED_DELETE_PATH]["delete"]["parameters"][0]
    assert parameter == {"$ref": "#/components/parameters/DeviceId"}
    documented = _spec()["components"]["parameters"]["DeviceId"]
    assert documented["in"] == "path"
    assert documented["required"] is True
    assert documented["schema"] == {"type": "string", "format": "uuid"}


def test_a_renamed_contract_field_fails_the_gate(tmp_path, monkeypatch):
    """The gate is only worth having if it can fail."""
    spec_path = _locate_spec()
    if spec_path is None:
        pytest.skip("notification.openapi.yaml not found (local run)")

    platform = "        platform:\n          $ref: '#/components/schemas/DevicePlatform'\n"
    mutated = spec_path.read_text(encoding="utf-8").replace(
        platform + "        token:", platform + "        pushToken:"
    )
    target = tmp_path / "notification.openapi.yaml"
    target.write_text(mutated, encoding="utf-8")
    monkeypatch.setenv("NOTIFICATION_OPENAPI_SPEC", str(target))

    with pytest.raises(AssertionError):
        test_the_documented_schema_matches_the_model("RegisterDevice", RegisterDeviceRequest)
