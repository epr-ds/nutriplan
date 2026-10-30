"""AIA-806 telemetry tests: metrics exposition, request tracing, structured access logs."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _scrape(client: TestClient) -> dict[str, float]:
    """Parse the Prometheus text exposition into ``{series: value}``."""
    values: dict[str, float] = {}
    for line in client.get("/metrics").text.splitlines():
        if not line or line.startswith("#"):
            continue
        series, _, raw = line.rpartition(" ")
        try:
            values[series] = float(raw)
        except ValueError:
            continue
    return values


def _series(name: str, **labels: str) -> str:
    if not labels:
        return name
    inner = ",".join(f'{key}="{value}"' for key, value in labels.items())
    return f"{name}{{{inner}}}"


def _value(client: TestClient, name: str, **labels: str) -> float:
    return _scrape(client).get(_series(name, **labels), 0.0)


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "ai_http_requests_total" in body
    assert "ai_http_request_duration_seconds" in body


def test_http_requests_are_counted_by_status() -> None:
    before = _value(client, "ai_http_requests_total", method="GET", route="/health", status="200")
    assert client.get("/health").status_code == 200
    assert (
        _value(client, "ai_http_requests_total", method="GET", route="/health", status="200")
        == before + 1
    )


def test_http_request_duration_is_observed() -> None:
    assert "ai_http_request_duration_seconds" in client.get("/metrics").text
    client.get("/health")
    assert "ai_http_request_duration_seconds_bucket" in client.get("/metrics").text


def test_request_ids_are_generated_and_returned() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
