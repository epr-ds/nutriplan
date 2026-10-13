"""HTTP surface of the scaffold (NTF-101, AC1).

Liveness must answer even when every dependency is down -- it reports that the *process*
is alive, and an orchestrator that conflates the two would restart a pod whose only
problem is a missing config value.
"""

from fastapi.testclient import TestClient

from app.api import health as health_module
from app.core.config import Settings
from app.main import app

client = TestClient(app)


def _settings(**overrides: object) -> Settings:
    """Build settings without reading the ambient environment."""
    base: dict[str, object] = {
        "environment": "development",
        "redis_url": "",
        "event_bus_url": "",
        "push_enabled": True,
        "fcm_project_id": "",
        "fcm_credentials_json": "",
        "apns_team_id": "",
        "apns_key_id": "",
        "apns_private_key": "",
    }
    base.update(overrides)
    return Settings(**base)


def test_health_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_ok() -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["service"] == "NutriPlan Notification Service"


def test_readiness_reports_every_check() -> None:
    response = client.get("/health/ready")

    # The default (development) environment comes up ready on a bare checkout.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {check["name"] for check in body["checks"]} == {
        "redis",
        "event_bus",
        "push_providers",
    }
    assert all(set(check) == {"name", "status", "detail"} for check in body["checks"])


def test_readiness_is_503_when_a_dependency_is_missing(monkeypatch) -> None:
    """A production pod with nothing wired must be pulled out of rotation, not serve."""
    monkeypatch.setattr(health_module, "settings", _settings(environment="production"))

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert {check["status"] for check in body["checks"]} == {"fail"}


def test_liveness_still_answers_when_readiness_fails(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "settings", _settings(environment="production"))

    assert client.get("/health/ready").status_code == 503
    assert client.get("/health").status_code == 200


def test_readiness_reports_an_unreachable_dependency(monkeypatch) -> None:
    """A configured Redis that will not answer takes the pod out of rotation."""
    monkeypatch.setattr(
        health_module,
        "settings",
        _settings(redis_url="redis://127.0.0.1:1/0", push_enabled=False),
    )

    def boom() -> None:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(health_module, "build_redis_probe", lambda _settings: boom)
    monkeypatch.setattr(health_module, "build_bus_probe", lambda _settings: boom)

    response = client.get("/health/ready")

    assert response.status_code == 503
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["redis"]["status"] == "fail"
    assert "ConnectionError" in checks["redis"]["detail"]
    assert checks["push_providers"]["status"] == "ok"
