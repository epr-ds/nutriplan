from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_ok() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_readiness_reports_checks() -> None:
    response = client.get("/health/ready")

    # The default (development) environment comes up ready even without an LLM key.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    names = {check["name"] for check in body["checks"]}
    assert "llm_provider" in names
