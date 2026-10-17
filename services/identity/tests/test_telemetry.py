"""IDN-804 telemetry tests: metrics exposition, request tracing, structured access logs."""

import logging

from fastapi.testclient import TestClient

EMAIL = "telemetry@example.com"
PASSWORD = "supersecret-password"
REGISTER = {"email": EMAIL, "password": PASSWORD, "name": "Telemetry"}


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


def test_metrics_endpoint_exposes_prometheus_format(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "identity_auth_events_total" in body
    assert "identity_http_request_duration_seconds" in body


def test_login_outcomes_are_counted(client: TestClient) -> None:
    client.post("/auth/register", json=REGISTER)

    before_ok = _value(client, "identity_auth_events_total", event="login_success")
    assert (
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    )
    assert _value(client, "identity_auth_events_total", event="login_success") == before_ok + 1

    before_bad = _value(client, "identity_auth_events_total", event="login_failure")
    assert (
        client.post("/auth/login", json={"email": EMAIL, "password": "wrong-password"}).status_code
        == 401
    )
    assert _value(client, "identity_auth_events_total", event="login_failure") == before_bad + 1


def test_rejected_auth_is_counted_by_status(client: TestClient) -> None:
    client.post("/auth/register", json=REGISTER)
    before = _value(client, "identity_auth_errors_total", status="401")
    client.post("/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert _value(client, "identity_auth_errors_total", status="401") == before + 1


def test_http_requests_are_counted_by_status(client: TestClient) -> None:
    before = _value(
        client, "identity_http_requests_total", method="GET", route="/health", status="200"
    )
    client.get("/health")
    after = _value(
        client, "identity_http_requests_total", method="GET", route="/health", status="200"
    )
    assert after == before + 1


def test_request_latency_is_observed(client: TestClient) -> None:
    before = _value(
        client, "identity_http_request_duration_seconds_count", method="GET", route="/health"
    )
    client.get("/health")
    after = _value(
        client, "identity_http_request_duration_seconds_count", method="GET", route="/health"
    )
    assert after == before + 1


def test_request_id_is_preserved_or_generated(client: TestClient) -> None:
    echoed = client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert echoed.headers["X-Request-ID"] == "req-abc-123"

    generated = client.get("/health")
    assert generated.headers["X-Request-ID"]


def test_inbound_traceparent_is_adopted_in_logs(client: TestClient, caplog) -> None:
    trace_id = "0" * 31 + "1"
    with caplog.at_level(logging.INFO, logger="identity.request"):
        client.get(
            "/health",
            headers={"traceparent": f"00-{trace_id}-{'1' * 16}-01"},
        )
    records = [record for record in caplog.records if record.name == "identity.request"]
    assert records
    assert any(getattr(record, "trace_id", None) == trace_id for record in records)


def test_access_log_carries_request_context(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="identity.request"):
        client.get("/health")
    record = next(r for r in caplog.records if r.name == "identity.request")
    assert getattr(record, "request_id", None)
    assert getattr(record, "status", None) == 200
    assert getattr(record, "method", None) == "GET"
