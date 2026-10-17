"""Edge hardening tests for the notification service (NTF-702): rate limit + CORS.

The repository and token verifier are stubbed so these exercise the real routers, the
rate-limit dependency, and the CORS middleware with no Redis and no network.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.api.deps import get_notification_repository, get_token_verifier
from app.core import ratelimit
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.main import app, create_app

ORIGIN = "https://app.nutriplan.mx"
_ACAO = "access-control-allow-origin"
_PROBLEM_JSON = "application/problem+json"

PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
TOKEN = "good-token"


class _StubVerifier:
    def verify(self, token: str) -> Principal:
        if token != TOKEN:
            raise InvalidTokenError("unknown token")
        return PRINCIPAL


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_notification_repository] = lambda: InMemoryNotificationRepository()
    app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_notification_repository, None)
        app.dependency_overrides.pop(get_token_verifier, None)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


# -- rate limiting -------------------------------------------------------------------


def test_it_returns_429_once_the_allowance_is_spent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    ratelimit.reset_rate_limit()

    for _ in range(2):
        assert client.get("/notifications", headers=_auth()).status_code == 200

    blocked = client.get("/notifications", headers=_auth())

    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith(_PROBLEM_JSON)
    assert blocked.headers.get("Retry-After")


def test_the_limit_can_be_switched_off(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    ratelimit.reset_rate_limit()

    for _ in range(3):
        assert client.get("/notifications", headers=_auth()).status_code == 200


# -- CORS ----------------------------------------------------------------------------


def test_no_cors_headers_without_an_allow_list() -> None:
    cors_client = TestClient(create_app())

    response = cors_client.get("/", headers={"Origin": ORIGIN})

    assert _ACAO not in response.headers


def test_the_allowed_origin_is_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    cors_client = TestClient(create_app())

    response = cors_client.get("/", headers={"Origin": ORIGIN})

    assert response.headers.get(_ACAO) == ORIGIN


def test_a_preflight_is_answered_for_an_allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    cors_client = TestClient(create_app())

    response = cors_client.options(
        "/notifications",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get(_ACAO) == ORIGIN


def test_an_unlisted_origin_is_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    cors_client = TestClient(create_app())

    response = cors_client.get("/", headers={"Origin": "https://evil.example"})

    assert _ACAO not in response.headers
