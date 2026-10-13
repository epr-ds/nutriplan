def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_with_db(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_readiness_reports_grocery_circuit_breakers(client):
    """COM-407: breaker state is observable through the readiness probe."""
    body = client.get("/health/ready").json()
    assert isinstance(body["groceryProviders"], list)
    for entry in body["groceryProviders"]:
        assert set(entry) == {"id", "state", "consecutiveFailures", "secondsUntilRetry"}
        assert entry["state"] in {"closed", "open", "half_open"}


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
