"""NTF-302 API tests for the device-token router (no Redis, no network).

The genuine router, validation, auth dependency, error mapping, and wire projection run
against the real in-memory adapter; adapter parity is proven separately in
``test_device_token_store.py``.

Two groups are worth reading closely. The ownership cases pin that a device registered by
one account cannot be revoked by another, and that the answer is ``404`` rather than ``403``
so the id cannot be probed. The idempotency cases pin that a launch-time re-register is a
refresh -- same id, no second row -- because that is the path clients take most often.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_device_token_repository import InMemoryDeviceTokenRepository
from app.api.deps import get_device_token_repository, get_token_verifier
from app.core.principal import Principal
from app.domain.enums import DevicePlatform
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
OTHER_TOKEN = "other-token"

PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
OTHER_PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="b@b.com")

USER = uuid.UUID(PRINCIPAL.user_id)
OTHER_USER = uuid.UUID(OTHER_PRINCIPAL.user_id)

PATH = "/notifications/devices"
PROBLEM_JSON = "application/problem+json"
ANDROID = DevicePlatform.ANDROID
IOS = DevicePlatform.IOS
DEVICE_TOKEN = "fcm-token-abc123"


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_device_token_repository, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build() -> tuple[TestClient, InMemoryDeviceTokenRepository]:
    repository = InMemoryDeviceTokenRepository()
    app.dependency_overrides[get_device_token_repository] = lambda: repository
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier(
        {GOOD_TOKEN: PRINCIPAL, OTHER_TOKEN: OTHER_PRINCIPAL}
    )
    return TestClient(app), repository


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(
    client: TestClient,
    *,
    token: str = GOOD_TOKEN,
    platform: str = "android",
    device_token: str = DEVICE_TOKEN,
):
    return client.post(
        PATH,
        headers=_auth(token),
        json={"platform": platform, "token": device_token},
    )


# -- registering ------------------------------------------------------------------------


def test_a_new_token_is_registered():
    client, _ = _build()

    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["platform"] == "android"
    assert body["createdAt"] == body["updatedAt"]


def test_the_response_does_not_echo_the_token():
    """The client just sent it; repeating it only gives it another place to be logged."""
    client, _ = _build()

    assert "token" not in _register(client).json()


def test_re_registering_the_same_token_returns_the_same_id():
    client, repository = _build()
    first = _register(client).json()

    second = _register(client).json()

    assert second["id"] == first["id"]
    assert second["createdAt"] == first["createdAt"]
    assert len(repository.list_for_user(USER)) == 1


def test_the_platform_is_part_of_the_identity():
    """The same string from FCM and APNs addresses two different providers."""
    client, repository = _build()
    android = _register(client, platform="android").json()

    ios = _register(client, platform="ios").json()

    assert ios["id"] != android["id"]
    assert len(repository.list_for_user(USER)) == 2


def test_a_token_that_changes_accounts_moves_to_the_new_owner():
    client, repository = _build()
    original = _register(client).json()

    moved = _register(client, token=OTHER_TOKEN).json()

    assert moved["id"] == original["id"]
    assert repository.list_for_user(USER) == []
    assert len(repository.list_for_user(OTHER_USER)) == 1


def test_platforms_are_projected_to_their_wire_values():
    client, _ = _build()

    assert _register(client, platform="ios").json()["platform"] == IOS.value


# -- revoking ---------------------------------------------------------------------------


def test_revoking_an_owned_device_returns_204():
    client, _ = _build()
    device_id = _register(client).json()["id"]

    response = client.delete(f"{PATH}/{device_id}", headers=_auth())

    assert response.status_code == 204
    assert response.content == b""


def test_revoking_a_device_twice_is_not_found():
    client, _ = _build()
    device_id = _register(client).json()["id"]
    client.delete(f"{PATH}/{device_id}", headers=_auth())

    response = client.delete(f"{PATH}/{device_id}", headers=_auth())

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_another_users_device_cannot_be_revoked():
    """``404`` rather than ``403``: the caller must not learn that the id exists at all."""
    client, repository = _build()
    device_id = _register(client).json()["id"]

    response = client.delete(f"{PATH}/{device_id}", headers=_auth(OTHER_TOKEN))

    assert response.status_code == 404
    assert len(repository.list_for_user(USER)) == 1


def test_an_unknown_device_id_is_not_found():
    client, _ = _build()

    response = client.delete(f"{PATH}/{uuid.uuid4()}", headers=_auth())

    assert response.status_code == 404


def test_a_non_uuid_device_id_is_422():
    client, _ = _build()

    response = client.delete(f"{PATH}/not-a-uuid", headers=_auth())

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


# -- authentication and validation ------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_no_token_is_401_problem_json(method):
    client, _ = _build()
    target = PATH if method == "POST" else f"{PATH}/{uuid.uuid4()}"

    response = client.request(
        method, target, headers={"Content-Type": "application/json"}, json={"platform": "ios"}
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_rejected_token_is_401():
    client, _ = _build()

    assert _register(client, token="nope").status_code == 401


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"platform": "windows", "token": "x"}, "unknown platform"),
        ({"token": "x"}, "platform is required"),
        ({"platform": "android"}, "token is required"),
        ({"platform": "android", "token": ""}, "blank token"),
        ({"platform": "android", "token": "   "}, "whitespace-only token"),
        ({"platform": "android", "token": "has space"}, "interior whitespace"),
        ({"platform": "android", "token": "x" * 4097}, "over the documented maximum"),
        ({"platform": "android", "token": 123}, "non-string token"),
    ],
)
def test_an_unusable_registration_is_422(body, reason):
    client, _ = _build()

    response = client.post(PATH, headers=_auth(), json=body)

    assert response.status_code == 422, reason
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_a_rejected_registration_stores_nothing():
    client, repository = _build()

    client.post(PATH, headers=_auth(), json={"platform": "android", "token": "   "})

    assert repository.list_for_user(USER) == []


# -- routing ----------------------------------------------------------------------------


def test_devices_resolves_to_the_devices_handler():
    """A literal under ``/notifications``, where the feed's parameterised routes live."""
    client, _ = _build()

    assert _register(client).status_code == 201


def test_the_feed_and_settings_routes_still_work_alongside_it():
    client, _ = _build()

    assert client.get("/notifications", headers=_auth()).status_code == 200
    assert client.get("/notifications/preferences", headers=_auth()).status_code == 200
