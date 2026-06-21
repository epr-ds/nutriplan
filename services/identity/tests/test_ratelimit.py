from app.core.config import settings
from app.core.ratelimit import reset_rate_limit


def test_auth_route_throttled_after_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 3)
    reset_rate_limit()

    payload = {"email": "ghost@example.com", "password": "whatever"}
    statuses = [client.post("/auth/login", json=payload).status_code for _ in range(4)]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429

    throttled = client.post("/auth/login", json=payload)
    assert throttled.status_code == 429
    assert "Retry-After" in throttled.headers
    assert throttled.headers["content-type"].startswith("application/problem+json")
    assert throttled.json()["status"] == 429

    reset_rate_limit()


def test_disabled_rate_limit_allows_many(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    reset_rate_limit()
    payload = {"email": "ghost2@example.com", "password": "whatever"}
    statuses = [client.post("/auth/login", json=payload).status_code for _ in range(10)]
    assert all(code == 401 for code in statuses)
