"""COM-902: the ``/commerce/*`` gateway edge.

The Commerce API is reached through the gateway under a single authenticated prefix
(``/commerce/v1/*``). The gateway owns the edge: it verifies the caller JWT via Identity's JWKS
endpoint and answers ``401`` at the edge before any commerce handler runs.

The API-level security tests in ``test_payment_methods.py`` already cover the handler-side
dependency. This suite pins the *edge*: the gateway prefix is the only path surface the mobile
client and the OpenAPI contract address (``https://api.nutriplan.app/commerce/v1``), and the
unauthenticated response is the gateway's own ``401`` (``WWW-Authenticate: Bearer`` + problem+json).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_ai_client,
    get_ai_rate_limiter,
    get_dietary_client,
    get_payment_method_service,
    get_token_verifier,
)
from app.application.payment_methods import PaymentMethodService
from app.core.principal import Principal
from app.domain.enums import PaymentMethodType
from app.domain.payment_method import SavedPaymentMethod
from app.main import app
from tests.fakes import InMemoryPaymentMethodRepository, StubVerifier

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)

_CARD_BODY: dict[str, Any] = {
    "type": "credit_card",
    "token": "tok_visa_secret",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


@pytest.fixture
def client() -> Iterator[tuple[TestClient, InMemoryPaymentMethodRepository]]:
    """A gateway-bound ``TestClient`` with the in-process fakes installed for one test.

    The app is a module-level singleton, so the overrides must be torn down afterwards -- a leaked
    override would silently swap the harness database for the in-memory fakes in later tests.
    """

    repo = InMemoryPaymentMethodRepository()
    app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.pop(get_payment_method_service, None)
        app.dependency_overrides.pop(get_token_verifier, None)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


# --------------------------------------------------------------------------- the gateway edge


def test_gateway_payment_methods_require_authentication(client) -> None:
    api_client, _repo = client
    response = api_client.get("/commerce/v1/payment-methods")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


def test_gateway_orders_require_authentication(client) -> None:
    api_client, _repo = client
    response = api_client.post(
        "/commerce/v1/orders",
        json={
            "mealPlanId": str(uuid.uuid4()),
            "fulfillmentType": "dark_kitchen",
            "deliveryAddress": {
                "street": "Av. Reforma 100",
                "city": "CDMX",
                "state": "CDMX",
                "zipCode": "06600",
                "country": "MX",
            },
            "deliveryDate": "2026-07-10",
            "deliveryTimeSlot": "12:00-13:00",
        },
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


def test_gateway_accepts_authenticated_commerce_call(client) -> None:
    """The edge passes a verified caller through to the commerce handler."""

    api_client, repo = client
    response = api_client.post("/commerce/v1/payment-methods", json=_CARD_BODY, headers=_auth())
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "credit_card"
    assert body["brand"] == "visa"
    # Security: the stored provider token is never echoed back to the client.
    assert "token" not in body
    assert "tok_visa_secret" not in response.text
    assert len(repo.list_for_user(USER)) == 1


def test_gateway_lists_payment_methods_for_authenticated_caller(client) -> None:
    api_client, repo = client
    repo.add(SavedPaymentMethod(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_secret"))
    response = api_client.get("/commerce/v1/payment-methods", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "paypal"
    assert "token" not in body[0]
    assert "tok_secret" not in response.text


def test_gateway_dietary_requires_authentication(client) -> None:
    """DPL-802: the ``/dietary`` gateway edge answers unauthenticated callers with 401."""
    api_client, _repo = client
    response = api_client.get("/dietary/recipes")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


class FakeDietaryClient:
    """Minimal httpx.Client stand-in recording forwarded calls (DPL-802)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append(
            {"method": method, "url": url, "headers": dict(kwargs.get("headers") or {})}
        )
        return httpx.Response(200, json={"ok": True})


def test_gateway_dietary_proxies_to_dietary_service(client) -> None:
    """DPL-802: the edge relays the verified caller to the Dietary service via bearer token."""
    api_client, _repo = client
    fake = FakeDietaryClient()
    app.dependency_overrides[get_dietary_client] = lambda: fake
    try:
        response = api_client.get("/dietary/meal-plans/abc", headers=_auth())
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert len(fake.calls) == 1
        assert fake.calls[0]["method"] == "GET"
        assert fake.calls[0]["url"] == "/meal-plans/abc"
        assert fake.calls[0]["headers"]["Authorization"] == f"Bearer {GOOD_TOKEN}"
    finally:
        app.dependency_overrides.pop(get_dietary_client, None)


# --------------------------------------------------------------------------- the AI gateway edge


def test_gateway_ai_requires_authentication(client) -> None:
    """AIA-804: the ``/ai`` gateway edge answers unauthenticated callers with 401."""
    api_client, _repo = client
    response = api_client.get("/ai/optimize-plan")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


class FakeAiClient:
    """Minimal httpx.Client stand-in recording forwarded calls (AIA-804)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append(
            {"method": method, "url": url, "headers": dict(kwargs.get("headers") or {})}
        )
        return httpx.Response(200, json={"ok": True})


def test_gateway_ai_proxies_to_ai_service(client) -> None:
    """AIA-804: the edge relays the verified caller to the AI service via bearer token."""
    api_client, _repo = client
    fake = FakeAiClient()
    app.dependency_overrides[get_ai_client] = lambda: fake
    try:
        response = api_client.post(
            "/ai/optimize-plan", json={"goal": "lower sugar"}, headers=_auth()
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert len(fake.calls) == 1
        assert fake.calls[0]["method"] == "POST"
        assert fake.calls[0]["url"] == "/ai/optimize-plan"
        assert fake.calls[0]["headers"]["Authorization"] == f"Bearer {GOOD_TOKEN}"
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


class FakeAiRateLimiter:
    """Stand-in rate limiter: the first call is allowed, later calls within a user are not."""

    def __init__(self) -> None:
        self.allowances: list[str] = []

    def allow(self, key: str) -> bool:
        self.allowances.append(key)
        return len(self.allowances) == 1


def test_gateway_ai_rate_limits_per_user(client) -> None:
    """AIA-804: the per-user edge rate limit answers 429 once the budget is spent."""
    api_client, _repo = client
    fake = FakeAiClient()
    limiter = FakeAiRateLimiter()
    app.dependency_overrides[get_ai_client] = lambda: fake
    app.dependency_overrides[get_ai_rate_limiter] = lambda: limiter
    try:
        first = api_client.post("/ai/optimize-plan", json={"goal": "lower sugar"}, headers=_auth())
        second = api_client.post("/ai/optimize-plan", json={"goal": "lower sugar"}, headers=_auth())
        assert first.status_code == 200
        assert second.status_code == 429
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
        app.dependency_overrides.pop(get_ai_rate_limiter, None)
