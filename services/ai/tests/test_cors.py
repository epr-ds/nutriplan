"""CORS configuration tests for the AI edge (AIA-804)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

ORIGIN = "https://app.nutriplan.mx"
_ACAO = "access-control-allow-origin"


def test_no_cors_headers_without_an_allow_list() -> None:
    client = TestClient(create_app())

    response = client.get("/", headers={"Origin": ORIGIN})

    assert _ACAO not in response.headers


def test_the_allowed_origin_is_echoed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    client = TestClient(create_app())

    response = client.get("/", headers={"Origin": ORIGIN})

    assert response.headers.get(_ACAO) == ORIGIN


def test_a_preflight_is_answered_for_an_allowed_origin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    client = TestClient(create_app())

    response = client.options(
        "/ai/recommendations",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get(_ACAO) == ORIGIN


def test_an_unlisted_origin_is_not_echoed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_allow_origins", ORIGIN)
    client = TestClient(create_app())

    response = client.get("/", headers={"Origin": "https://evil.example"})

    assert _ACAO not in response.headers
