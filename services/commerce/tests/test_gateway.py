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

from fastapi.testclient import TestClient

from app.api.deps import get_payment_method_service, get_token_verifier
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

_CARD_BODY = {
    "type": "credit_card",
    "token": "tok_visa_secret",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


def _build() -> tuple[TestClient, InMemoryPaymentMethodRepository]:
    repo = InMemoryPaymentMethodRepository()
    app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


# --------------------------------------------------------------------------- the gateway edge


def test_gateway_payment_methods_require_authentication():
    client, _ = _build()
    response = client.get("/commerce/v1/payment-methods")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_JSON


def test_gateway_orders_require_authentication():
    client, _ = _build()
    response = client.post(
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


def test_gateway_accepts_authenticated_commerce_call():
    """The edge passes a verified caller through to the commerce handler."""

    client, repo = _build()
    response = client.post("/commerce/v1/payment-methods", json=_CARD_BODY, headers=_auth())
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "credit_card"
    assert body["brand"] == "visa"
    # Security: the stored provider token is never echoed back to the client.
    assert "token" not in body
    assert "tok_visa_secret" not in response.text
    assert len(repo.list_for_user(USER)) == 1


def test_gateway_lists_payment_methods_for_authenticated_caller():
    client, repo = _build()
    repo.add(SavedPaymentMethod(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_secret"))
    response = client.get("/commerce/v1/payment-methods", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "paypal"
    assert "token" not in body[0]
    assert "tok_secret" not in response.text
