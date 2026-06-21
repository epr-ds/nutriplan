"""Provider contract tests (IDN-701).

Verify that the Identity service's *actual* responses conform to the published
``contracts/identity.openapi.yaml`` — every documented operation is driven to each
response it declares (happy path + documented errors) and the real response is
validated against the contract with ``openapi-core``. A breaking change (renamed/
removed field, changed type, undocumented status, drifted error shape) makes a test
fail, which gates the PR in Backend CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

HOST = "http://localhost:8081"

# The service returns RFC 7807 errors as application/problem+json; teach openapi-core to
# deserialize that media type (it only knows application/json out of the box).
_EXTRA_DESERIALIZERS = {"application/problem+json": json.loads}


def _locate_spec() -> Path | None:
    if env := os.getenv("IDENTITY_OPENAPI_SPEC"):
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    # Walk up from this file (…/services/identity/tests) to the repo root, where the
    # contract lives at contracts/identity.openapi.yaml. Also covers a /contracts mount
    # (root is an ancestor), regardless of how deep the checkout/mount is.
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "contracts" / "identity.openapi.yaml"
        if candidate.is_file():
            return candidate
    return None


_SPEC_PATH = _locate_spec()

if _SPEC_PATH is None:
    # In CI the contract is always checked out, so a miss means the gate is mis-wired —
    # fail loudly. Locally (e.g. a bare in-image run without the contract mounted) skip.
    if os.getenv("CI"):
        raise RuntimeError(
            "Provider contract tests could not locate contracts/identity.openapi.yaml in CI. "
            "Set IDENTITY_OPENAPI_SPEC or ensure the contract is checked out."
        )
    pytest.skip(
        "identity.openapi.yaml not found; set IDENTITY_OPENAPI_SPEC or mount /contracts",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    config = Config(extra_media_type_deserializers=_EXTRA_DESERIALIZERS)
    return OpenAPI.from_file_path(str(_SPEC_PATH), config=config)


def assert_conforms(openapi: OpenAPI, method: str, path: str, response) -> None:
    """Validate a captured TestClient response against the contract for method+path."""
    content_type = response.headers.get("content-type", "application/json").split(";")[0].strip()
    request = MockRequest(host_url=HOST, method=method.lower(), path=path)
    mock_response = MockResponse(
        data=response.content,
        status_code=response.status_code,
        content_type=content_type,
    )
    openapi.validate_response(request, mock_response)


def _register(client, email: str = "contract@example.com"):
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret", "name": "Contract"},
    )
    assert resp.status_code == 201, resp.text
    return resp


def _auth_headers(client, email: str = "contract@example.com"):
    body = _register(client, email).json()
    return {"Authorization": f"Bearer {body['accessToken']}"}, body


# --- Auth -------------------------------------------------------------------


def test_register_response_conforms(openapi, client):
    resp = _register(client)
    assert_conforms(openapi, "post", "/auth/register", resp)


def test_register_duplicate_conforms(openapi, client):
    _register(client, "dupe@example.com")
    resp = client.post(
        "/auth/register",
        json={"email": "dupe@example.com", "password": "supersecret", "name": "Dupe"},
    )
    assert resp.status_code == 409
    assert_conforms(openapi, "post", "/auth/register", resp)


def test_login_response_conforms(openapi, client):
    _register(client, "login@example.com")
    resp = client.post(
        "/auth/login", json={"email": "login@example.com", "password": "supersecret"}
    )
    assert resp.status_code == 200
    assert_conforms(openapi, "post", "/auth/login", resp)


def test_login_invalid_conforms(openapi, client):
    _register(client, "badlogin@example.com")
    resp = client.post(
        "/auth/login", json={"email": "badlogin@example.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/auth/login", resp)


def test_refresh_response_conforms(openapi, client):
    tokens = _register(client, "refresh@example.com").json()
    resp = client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 200
    assert_conforms(openapi, "post", "/auth/refresh", resp)


# --- Users ------------------------------------------------------------------


def test_get_me_conforms(openapi, client):
    headers, _ = _auth_headers(client, "me@example.com")
    resp = client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    # Fresh account: avatarUrl and dietaryPreferences are null — exercises nullable fields.
    assert resp.json()["avatarUrl"] is None
    assert_conforms(openapi, "get", "/users/me", resp)


def test_update_profile_conforms(openapi, client):
    headers, _ = _auth_headers(client, "update@example.com")
    resp = client.put("/users/me", json={"name": "Renamed"}, headers=headers)
    assert resp.status_code == 200
    assert_conforms(openapi, "put", "/users/me", resp)


def test_update_dietary_preferences_conforms(openapi, client):
    headers, _ = _auth_headers(client, "diet@example.com")
    # Partial update: the unset fields come back null — exercises nullable preference fields.
    resp = client.put(
        "/users/me/dietary-preferences",
        json={"dietType": "vegan", "dailyCalorieTarget": 2000},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["macroTargets"] is None
    assert_conforms(openapi, "put", "/users/me/dietary-preferences", resp)


def test_avatar_upload_url_conforms(openapi, client):
    headers, _ = _auth_headers(client, "avatar1@example.com")
    resp = client.post(
        "/users/me/avatar-upload-url", json={"contentType": "image/png"}, headers=headers
    )
    assert resp.status_code == 200
    assert_conforms(openapi, "post", "/users/me/avatar-upload-url", resp)


def test_set_avatar_conforms(openapi, client):
    headers, _ = _auth_headers(client, "avatar2@example.com")
    key = client.post(
        "/users/me/avatar-upload-url", json={"contentType": "image/png"}, headers=headers
    ).json()["key"]
    resp = client.put("/users/me/avatar", json={"key": key}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["avatarUrl"] is not None
    assert_conforms(openapi, "put", "/users/me/avatar", resp)


def test_set_avatar_forbidden_conforms(openapi, client):
    headers, _ = _auth_headers(client, "avatar3@example.com")
    resp = client.put(
        "/users/me/avatar",
        json={"key": "00000000-0000-0000-0000-000000000000/x.png"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert_conforms(openapi, "put", "/users/me/avatar", resp)
