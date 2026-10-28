"""HRD-101: automated security regression tests for the backend gateway HTTP boundary.

Where the existing gateway tests pin *unauthenticated* callers (401) and the happy path, this
module pins the *invalid-token* half of the boundary: a caller presenting a malformed bearer
token must be rejected with ``401`` before any proxying happens.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_payment_method_service, get_token_verifier
from app.application.payment_methods import PaymentMethodService
from app.core.principal import Principal
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
    """A gateway-bound ``TestClient`` with the in-process fakes installed for one test."""

    repo = InMemoryPaymentMethodRepository()
    app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.pop(get_payment_method_service, None)
        app.dependency_overrides.pop(get_token_verifier, None)


def test_gateway_rejects_an_invalid_bearer_token(client) -> None:
    api_client, _repo = client
    response = api_client.post(
        "/commerce/v1/payment-methods",
        json=_CARD_BODY,
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


def test_gateway_does_not_proxy_an_invalid_bearer_token(client) -> None:
    """An invalid token must never be forwarded upstream (it is not a verified caller)."""

    api_client, repo = client
    response = api_client.post(
        "/commerce/v1/payment-methods",
        json=_CARD_BODY,
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401
    assert len(repo.list_for_user(USER)) == 0
