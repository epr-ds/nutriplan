"""Provider contract tests for the Commerce service (COM-802).

Verify that the Commerce service's *actual* responses conform to the published
``contracts/commerce.openapi.yaml``: every implemented operation is driven to each response it
documents (happy path + documented errors) and the real response is validated against the contract
with ``openapi-core``, problem+json error bodies included. A breaking change (renamed/removed
required field, changed type, drifted enum, a ``null`` the contract does not allow, an undocumented
status) makes a test fail, which gates the PR in Backend CI (``backend.yml`` commerce-service job).

The endpoints run through the real routers, schemas, services and SQL repositories on the COM-801
harness database (SQLite, a Postgres service container, or Testcontainers). Only what lies outside
the service is replaced: the bearer-token check, the Dietary meal-plan lookup, the payment
provider's webhook secret, the kitchen webhook secret, and (for the outage case) a grocery adapter.
The payment provider and grocery adapters are the in-process fakes dev and CI already run on.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

from app.adapters.kitchen_webhook_verifier import KitchenWebhookVerifier
from app.api.deps import (
    get_grocery_adapters,
    get_kitchen_webhook_verifier,
    get_meal_plan_provider,
    get_payment_provider,
    get_token_verifier,
)
from app.core.principal import Principal
from app.domain.enums import OrderStatus
from app.domain.errors import GroceryProviderUnavailableError, MealPlanUnavailableError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.main import app
from app.payments.fake import FakePaymentProvider
from app.repositories.sql_order_repository import SqlOrderRepository
from tests.fakes import StubVerifier
from tests.seed import SEED_USER_ID, build_kitchen_order, seed_orders

HOST = "http://localhost:8083"
TOKEN = "contract-token"
_AUTH = {"Authorization": f"Bearer {TOKEN}"}
_PROBLEM_JSON = "application/problem+json"
_PAYMENT_SECRET = "contract-payment-webhook-secret"  # gitleaks:allow
_KITCHEN_SECRET = "contract-kitchen-webhook-secret"  # gitleaks:allow
_MISSING_ID = "99999999-9999-4999-8999-999999999999"
_PLAN_ID = str(uuid.UUID("22222222-3333-4444-8555-666666666666"))


def _locate_spec() -> Path | None:
    if env := os.getenv("COMMERCE_OPENAPI_SPEC"):
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    # Walk up from this file (.../services/commerce/tests) to the repo root, where the contract
    # lives at contracts/commerce.openapi.yaml. Also covers a /contracts mount (compose).
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "contracts" / "commerce.openapi.yaml"
        if candidate.is_file():
            return candidate
    return None


_SPEC_PATH = _locate_spec()

if _SPEC_PATH is None:
    # In CI the contract is always checked out, so a miss means the gate is mis-wired -- fail
    # loudly. Locally (e.g. a bare in-image run without the contract mounted) skip.
    if os.getenv("CI"):
        raise RuntimeError(
            "Provider contract tests could not locate contracts/commerce.openapi.yaml in CI. "
            "Set COMMERCE_OPENAPI_SPEC or ensure the contract is checked out."
        )
    pytest.skip(
        "commerce.openapi.yaml not found; set COMMERCE_OPENAPI_SPEC or mount /contracts",
        allow_module_level=True,
    )


def _config() -> Config:
    # Errors are ``application/problem+json`` (RFC 7807, COM-108); teach openapi-core to
    # deserialize that media type so error bodies are validated against ``Problem``.
    return Config(extra_media_type_deserializers={_PROBLEM_JSON: json.loads})


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH), config=_config())


def assert_conforms(openapi: OpenAPI, method: str, path: str, response) -> None:
    """Validate a captured TestClient response against the contract for method+path."""
    content_type = response.headers.get("content-type", "application/json").split(";")[0].strip()
    openapi.validate_response(
        MockRequest(host_url=HOST, method=method.lower(), path=path),
        MockResponse(
            data=response.content, status_code=response.status_code, content_type=content_type
        ),
    )


# --- service doubles ----------------------------------------------------------------------------


class _MealPlans:
    """A Dietary stand-in whose answer each test can set: a plan, no plan, or an outage."""

    def __init__(self) -> None:
        self.snapshot: MealPlanSnapshot | None = MealPlanSnapshot(
            plan_id=_PLAN_ID,
            meals=[
                PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oats"),
                PlannedMeal(meal_type="dinner", servings=Decimal("2"), recipe_name="Lentil soup"),
            ],
        )
        self.unavailable = False

    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None:
        if self.unavailable:
            raise MealPlanUnavailableError("Dietary is down")
        return self.snapshot


class _UnavailableGroceryAdapter:
    """A grocery adapter whose provider cannot be reached right now."""

    provider_id = "freshbasket"

    def search(self, query):
        raise GroceryProviderUnavailableError(self.provider_id)

    def place_order(self, request):
        raise GroceryProviderUnavailableError(self.provider_id)

    def get_order_status(self, external_order_id: str):
        raise GroceryProviderUnavailableError(self.provider_id)


@pytest.fixture
def meal_plans() -> _MealPlans:
    return _MealPlans()


@pytest.fixture
def api(client, meal_plans):
    """The real app on the harness database, with only the outside world replaced."""
    principal = Principal(user_id=str(SEED_USER_ID), email="contract.user@example.com")
    payments = FakePaymentProvider(webhook_secret=_PAYMENT_SECRET)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({TOKEN: principal})
    app.dependency_overrides[get_meal_plan_provider] = lambda: meal_plans
    app.dependency_overrides[get_payment_provider] = lambda: payments
    app.dependency_overrides[get_kitchen_webhook_verifier] = lambda: KitchenWebhookVerifier(
        _KITCHEN_SECRET
    )
    yield client
    for dependency in (
        get_token_verifier,
        get_meal_plan_provider,
        get_payment_provider,
        get_kitchen_webhook_verifier,
        get_grocery_adapters,
    ):
        app.dependency_overrides.pop(dependency, None)


def _order_body(*, payment: dict | None = None, **overrides) -> dict:
    body = {
        "mealPlanId": _PLAN_ID,
        "fulfillmentType": "pickup",
        "deliveryAddress": {
            "street": "Av. Reforma 222",
            "city": "Ciudad de Mexico",
            "state": "CDMX",
            "zipCode": "06600",
            "country": "MX",
        },
        "deliveryDate": "2026-11-02",
        "deliveryTimeSlot": "13:00-15:00",
        **overrides,
    }
    if payment is not None:
        body["paymentMethod"] = payment
    return body


def _create(api, **kwargs) -> dict:
    response = api.post("/orders", json=_order_body(**kwargs), headers=_AUTH)
    assert response.status_code == 201, response.text
    return response.json()


def _signed(secret: str, event: dict) -> tuple[bytes, dict[str, str]]:
    payload = json.dumps(event).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return payload, {"X-Webhook-Signature": signature, "Content-Type": "application/json"}


# --- POST /orders -------------------------------------------------------------------------------


def test_create_order_conforms(openapi, api):
    resp = api.post("/orders", json=_order_body(notes="Contract order"), headers=_AUTH)
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    assert_conforms(openapi, "post", "/orders", resp)


@pytest.mark.parametrize(
    ("payment", "member"),
    [
        # No token: OXXO, SPEI and PayPal involve no card (COM-608).
        ({"type": "oxxo"}, "voucher"),
        ({"type": "spei"}, "transfer"),
        ({"type": "paypal"}, "approval"),
        # A token is still accepted from older clients, and ignored.
        ({"type": "oxxo", "token": "tok_oxxo"}, "voucher"),
    ],
)
def test_create_order_with_an_async_payment_conforms(openapi, api, payment, member):
    resp = api.post("/orders", json=_order_body(payment=payment), headers=_AUTH)
    assert resp.status_code == 201
    assert resp.json()[member] is not None
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_paid_by_card_conforms(openapi, api):
    payment = {"type": "credit_card", "token": "tok_visa"}
    resp = api.post("/orders", json=_order_body(payment=payment), headers=_AUTH)
    assert resp.status_code == 201
    assert resp.json()["status"] == "confirmed"
    assert_conforms(openapi, "post", "/orders", resp)


@pytest.mark.parametrize("token", [None, "", "  "])
def test_create_order_card_without_token_conforms(openapi, api, token):
    payment = {"type": "credit_card"} if token is None else {"type": "credit_card", "token": token}
    resp = api.post("/orders", json=_order_body(payment=payment), headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_declined_card_conforms(openapi, api):
    payment = {"type": "credit_card", "token": "tok_decline_insufficient"}
    resp = api.post("/orders", json=_order_body(payment=payment), headers=_AUTH)
    assert resp.status_code == 402
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_unknown_meal_plan_conforms(openapi, api, meal_plans):
    meal_plans.snapshot = None
    resp = api.post("/orders", json=_order_body(), headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_dietary_unavailable_conforms(openapi, api, meal_plans):
    meal_plans.unavailable = True
    resp = api.post("/orders", json=_order_body(), headers=_AUTH)
    assert resp.status_code == 503
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_idempotency_conflict_conforms(openapi, api):
    headers = {**_AUTH, "Idempotency-Key": "contract-key-1"}
    first = api.post("/orders", json=_order_body(), headers=headers)
    assert first.status_code == 201
    # The same key with a different body is a conflict, not a second order.
    resp = api.post("/orders", json=_order_body(notes="Different"), headers=headers)
    assert resp.status_code == 409
    assert_conforms(openapi, "post", "/orders", resp)


def test_create_order_validation_error_conforms(openapi, api):
    body = _order_body()
    del body["deliveryAddress"]
    resp = api.post("/orders", json=body, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/orders", resp)


def _quote_body(**overrides) -> dict:
    return {"mealPlanId": _PLAN_ID, "fulfillmentType": "dark_kitchen", **overrides}


def test_quote_order_conforms(openapi, api):
    resp = api.post("/orders/quote", json=_quote_body(), headers=_AUTH)
    assert resp.status_code == 200
    assert [item["name"] for item in resp.json()["items"]] == ["Oats", "Lentil soup"]
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_quote_grocery_order_conforms(openapi, api):
    body = _quote_body(fulfillmentType="grocery_delivery", providerId="freshbasket")
    resp = api.post("/orders/quote", json=body, headers=_AUTH)
    assert resp.status_code == 200
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_quote_order_unknown_meal_plan_conforms(openapi, api, meal_plans):
    meal_plans.snapshot = None
    resp = api.post("/orders/quote", json=_quote_body(), headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_quote_order_dietary_unavailable_conforms(openapi, api, meal_plans):
    meal_plans.unavailable = True
    resp = api.post("/orders/quote", json=_quote_body(), headers=_AUTH)
    assert resp.status_code == 503
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_quote_order_validation_error_conforms(openapi, api):
    body = _quote_body(fulfillmentType="grocery_delivery")
    resp = api.post("/orders/quote", json=body, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_quote_order_unauthenticated_conforms(openapi, api):
    resp = api.post("/orders/quote", json=_quote_body())
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/orders/quote", resp)


def test_create_order_unauthenticated_conforms(openapi, api):
    resp = api.post("/orders", json=_order_body())
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith(_PROBLEM_JSON)
    assert_conforms(openapi, "post", "/orders", resp)


# --- GET /orders and GET /orders/{orderId} ---------------------------------------------------


def test_list_orders_conforms(openapi, api, db_session):
    seed_orders(db_session)
    resp = api.get("/orders", headers=_AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert_conforms(openapi, "get", "/orders", resp)


def test_list_orders_filtered_conforms(openapi, api, db_session):
    seed_orders(db_session)
    resp = api.get("/orders", params={"status": "confirmed", "limit": 5}, headers=_AUTH)
    assert resp.status_code == 200
    assert [order["status"] for order in resp.json()] == ["confirmed"]
    assert_conforms(openapi, "get", "/orders", resp)


def test_list_orders_bad_paging_conforms(openapi, api):
    resp = api.get("/orders", params={"limit": 0}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "get", "/orders", resp)


def test_list_orders_unauthenticated_conforms(openapi, api):
    resp = api.get("/orders")
    assert resp.status_code == 401
    assert_conforms(openapi, "get", "/orders", resp)


def test_get_order_conforms(openapi, api, db_session):
    kitchen, grocery = seed_orders(db_session)
    for order in (kitchen, grocery):
        resp = api.get(f"/orders/{order.id}", headers=_AUTH)
        assert resp.status_code == 200
        assert_conforms(openapi, "get", f"/orders/{order.id}", resp)


def test_get_order_not_found_conforms(openapi, api):
    resp = api.get(f"/orders/{_MISSING_ID}", headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "get", f"/orders/{_MISSING_ID}", resp)


def test_get_order_unauthenticated_conforms(openapi, api):
    resp = api.get(f"/orders/{_MISSING_ID}")
    assert resp.status_code == 401
    assert_conforms(openapi, "get", f"/orders/{_MISSING_ID}", resp)


# --- POST /orders/{orderId}/cancel -----------------------------------------------------------


def test_cancel_order_conforms(openapi, api):
    order = _create(api)
    resp = api.post(f"/orders/{order['id']}/cancel", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert_conforms(openapi, "post", f"/orders/{order['id']}/cancel", resp)


def test_cancel_paid_order_with_partial_refund_conforms(openapi, api):
    order = _create(api, payment={"type": "credit_card", "token": "tok_visa"})
    resp = api.post(f"/orders/{order['id']}/cancel", json={"refundAmount": 5}, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["refund"]["status"] == "partial"
    assert_conforms(openapi, "post", f"/orders/{order['id']}/cancel", resp)


def test_cancel_order_twice_conforms(openapi, api):
    order = _create(api)
    api.post(f"/orders/{order['id']}/cancel", headers=_AUTH)
    resp = api.post(f"/orders/{order['id']}/cancel", headers=_AUTH)
    assert resp.status_code == 409
    assert_conforms(openapi, "post", f"/orders/{order['id']}/cancel", resp)


def test_cancel_with_refund_over_total_conforms(openapi, api):
    order = _create(api, payment={"type": "credit_card", "token": "tok_visa"})
    path = f"/orders/{order['id']}/cancel"
    resp = api.post(path, json={"refundAmount": 999999}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", path, resp)


def test_cancel_order_not_found_conforms(openapi, api):
    resp = api.post(f"/orders/{_MISSING_ID}/cancel", headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", f"/orders/{_MISSING_ID}/cancel", resp)


def test_cancel_order_unauthenticated_conforms(openapi, api):
    resp = api.post(f"/orders/{_MISSING_ID}/cancel")
    assert resp.status_code == 401
    assert_conforms(openapi, "post", f"/orders/{_MISSING_ID}/cancel", resp)


# --- POST /orders/{orderId}/grocery/sync ------------------------------------------------------


def test_sync_grocery_order_conforms(openapi, api, db_session):
    _, grocery = seed_orders(db_session)
    path = f"/orders/{grocery.id}/grocery/sync"
    resp = api.post(path, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["groceryOrder"]["externalOrderId"] == "FB-1001"
    assert_conforms(openapi, "post", path, resp)


def test_sync_unplaced_order_conforms(openapi, api, db_session):
    kitchen, _ = seed_orders(db_session)
    path = f"/orders/{kitchen.id}/grocery/sync"
    resp = api.post(path, headers=_AUTH)
    assert resp.status_code == 409
    assert_conforms(openapi, "post", path, resp)


def test_sync_provider_outage_conforms(openapi, api, db_session):
    _, grocery = seed_orders(db_session)
    app.dependency_overrides[get_grocery_adapters] = lambda: {
        "freshbasket": _UnavailableGroceryAdapter()
    }
    path = f"/orders/{grocery.id}/grocery/sync"
    resp = api.post(path, headers=_AUTH)
    assert resp.status_code == 503
    assert_conforms(openapi, "post", path, resp)


def test_sync_not_found_conforms(openapi, api):
    path = f"/orders/{_MISSING_ID}/grocery/sync"
    resp = api.post(path, headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", path, resp)


def test_sync_unauthenticated_conforms(openapi, api):
    path = f"/orders/{_MISSING_ID}/grocery/sync"
    resp = api.post(path)
    assert resp.status_code == 401
    assert_conforms(openapi, "post", path, resp)


# --- POST /webhooks/payments -----------------------------------------------------------------


def _payment_event(event_type: str, reference: str) -> dict:
    return {"type": event_type, "data": {"reference": reference, "charge_id": "ch_contract"}}


def test_payment_webhook_conforms(openapi, api):
    order = _create(api, payment={"type": "oxxo", "token": "tok_oxxo"})
    payload, headers = _signed(_PAYMENT_SECRET, _payment_event("payment.confirmed", order["id"]))
    resp = api.post("/webhooks/payments", content=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert_conforms(openapi, "post", "/webhooks/payments", resp)


def test_payment_webhook_contradictory_event_conforms(openapi, api):
    order = _create(api, payment={"type": "oxxo", "token": "tok_oxxo"})
    confirmed = _signed(_PAYMENT_SECRET, _payment_event("payment.confirmed", order["id"]))
    api.post("/webhooks/payments", content=confirmed[0], headers=confirmed[1])
    payload, headers = _signed(_PAYMENT_SECRET, _payment_event("payment.failed", order["id"]))
    resp = api.post("/webhooks/payments", content=payload, headers=headers)
    assert resp.status_code == 409
    assert_conforms(openapi, "post", "/webhooks/payments", resp)


def test_payment_webhook_unknown_order_conforms(openapi, api):
    payload, headers = _signed(_PAYMENT_SECRET, _payment_event("payment.confirmed", _MISSING_ID))
    resp = api.post("/webhooks/payments", content=payload, headers=headers)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", "/webhooks/payments", resp)


def test_payment_webhook_bad_signature_conforms(openapi, api):
    payload, _ = _signed(_PAYMENT_SECRET, _payment_event("payment.confirmed", _MISSING_ID))
    headers = {"X-Webhook-Signature": "0" * 64, "Content-Type": "application/json"}
    resp = api.post("/webhooks/payments", content=payload, headers=headers)
    assert resp.status_code == 400
    assert_conforms(openapi, "post", "/webhooks/payments", resp)


# --- POST /webhooks/kitchen ------------------------------------------------------------------


def _confirmed_kitchen_order(db_session) -> str:
    order = build_kitchen_order()
    order.status = OrderStatus.CONFIRMED
    return str(SqlOrderRepository(db_session).add(order).id)


def _kitchen_event(event_type: str, reference: str) -> dict:
    return {"type": event_type, "data": {"reference": reference}}


def test_kitchen_webhook_conforms(openapi, api, db_session):
    order_id = _confirmed_kitchen_order(db_session)
    payload, headers = _signed(_KITCHEN_SECRET, _kitchen_event("kitchen.preparing", order_id))
    resp = api.post("/webhooks/kitchen", content=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "preparing"
    assert_conforms(openapi, "post", "/webhooks/kitchen", resp)


def test_kitchen_webhook_out_of_order_conforms(openapi, api, db_session):
    order_id = _confirmed_kitchen_order(db_session)
    # Dispatched before it was ever preparing: an out-of-order report.
    payload, headers = _signed(_KITCHEN_SECRET, _kitchen_event("kitchen.dispatched", order_id))
    resp = api.post("/webhooks/kitchen", content=payload, headers=headers)
    assert resp.status_code == 409
    assert_conforms(openapi, "post", "/webhooks/kitchen", resp)


def test_kitchen_webhook_unknown_order_conforms(openapi, api):
    payload, headers = _signed(_KITCHEN_SECRET, _kitchen_event("kitchen.preparing", _MISSING_ID))
    resp = api.post("/webhooks/kitchen", content=payload, headers=headers)
    assert resp.status_code == 404
    assert_conforms(openapi, "post", "/webhooks/kitchen", resp)


def test_kitchen_webhook_bad_signature_conforms(openapi, api):
    payload, _ = _signed(_KITCHEN_SECRET, _kitchen_event("kitchen.preparing", _MISSING_ID))
    headers = {"X-Webhook-Signature": "0" * 64, "Content-Type": "application/json"}
    resp = api.post("/webhooks/kitchen", content=payload, headers=headers)
    assert resp.status_code == 400
    assert_conforms(openapi, "post", "/webhooks/kitchen", resp)


# --- /payment-methods ------------------------------------------------------------------------

_CARD = {
    "type": "credit_card",
    "token": "tok_contract_visa",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


def test_save_payment_method_conforms(openapi, api):
    resp = api.post("/payment-methods", json=_CARD, headers=_AUTH)
    assert resp.status_code == 201
    assert "token" not in resp.json()
    assert_conforms(openapi, "post", "/payment-methods", resp)


def test_save_wallet_payment_method_conforms(openapi, api):
    resp = api.post("/payment-methods", json={"type": "paypal", "token": "tok_pp"}, headers=_AUTH)
    assert resp.status_code == 201
    assert resp.json()["last4"] is None
    assert_conforms(openapi, "post", "/payment-methods", resp)


def test_save_payment_method_validation_error_conforms(openapi, api):
    resp = api.post("/payment-methods", json={**_CARD, "last4": "42"}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/payment-methods", resp)


def test_save_payment_method_unauthenticated_conforms(openapi, api):
    resp = api.post("/payment-methods", json=_CARD)
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/payment-methods", resp)


def test_list_payment_methods_conforms(openapi, api):
    api.post("/payment-methods", json=_CARD, headers=_AUTH)
    api.post("/payment-methods", json={"type": "paypal", "token": "tok_pp"}, headers=_AUTH)
    resp = api.get("/payment-methods", headers=_AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert_conforms(openapi, "get", "/payment-methods", resp)


def test_list_payment_methods_unauthenticated_conforms(openapi, api):
    resp = api.get("/payment-methods")
    assert resp.status_code == 401
    assert_conforms(openapi, "get", "/payment-methods", resp)


def test_delete_payment_method_conforms(openapi, api):
    saved = api.post("/payment-methods", json=_CARD, headers=_AUTH).json()
    path = f"/payment-methods/{saved['id']}"
    resp = api.delete(path, headers=_AUTH)
    assert resp.status_code == 204
    assert_conforms(openapi, "delete", path, resp)


def test_delete_payment_method_not_found_conforms(openapi, api):
    path = f"/payment-methods/{_MISSING_ID}"
    resp = api.delete(path, headers=_AUTH)
    assert resp.status_code == 404
    assert_conforms(openapi, "delete", path, resp)


def test_delete_payment_method_unauthenticated_conforms(openapi, api):
    path = f"/payment-methods/{_MISSING_ID}"
    resp = api.delete(path)
    assert resp.status_code == 401
    assert_conforms(openapi, "delete", path, resp)


# --- /fulfillment ------------------------------------------------------------------------------

_AVAILABILITY = "/fulfillment/dark-kitchen/availability"


def test_availability_served_zip_conforms(openapi, api):
    resp = api.get(_AVAILABILITY, params={"zipCode": "06600"}, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["available"] is True
    assert_conforms(openapi, "get", _AVAILABILITY, resp)


def test_availability_unserved_zip_conforms(openapi, api):
    resp = api.get(_AVAILABILITY, params={"zipCode": "99999"}, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["available"] is False
    assert_conforms(openapi, "get", _AVAILABILITY, resp)


def test_availability_bad_zip_conforms(openapi, api):
    resp = api.get(_AVAILABILITY, params={"zipCode": "abc"}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "get", _AVAILABILITY, resp)


def test_availability_unauthenticated_conforms(openapi, api):
    resp = api.get(_AVAILABILITY, params={"zipCode": "06600"})
    assert resp.status_code == 401
    assert_conforms(openapi, "get", _AVAILABILITY, resp)


def test_grocery_providers_conforms(openapi, api):
    resp = api.get("/fulfillment/grocery/providers", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()
    assert_conforms(openapi, "get", "/fulfillment/grocery/providers", resp)


def test_grocery_providers_unauthenticated_conforms(openapi, api):
    resp = api.get("/fulfillment/grocery/providers")
    assert resp.status_code == 401
    assert_conforms(openapi, "get", "/fulfillment/grocery/providers", resp)


def test_grocery_search_conforms(openapi, api):
    body = {"items": [{"ingredient": "rice", "quantity": 1, "unit": "kg"}], "zipCode": "06600"}
    resp = api.post("/fulfillment/grocery/search", json=body, headers=_AUTH)
    assert resp.status_code == 200
    assert_conforms(openapi, "post", "/fulfillment/grocery/search", resp)


def test_grocery_search_validation_error_conforms(openapi, api):
    body = {"items": [], "zipCode": "06600"}
    resp = api.post("/fulfillment/grocery/search", json=body, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/fulfillment/grocery/search", resp)


def test_grocery_search_unauthenticated_conforms(openapi, api):
    body = {"items": [{"ingredient": "rice"}], "zipCode": "06600"}
    resp = api.post("/fulfillment/grocery/search", json=body)
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/fulfillment/grocery/search", resp)


# --- the gate actually catches drift (COM-802 AC2) -------------------------------------------


def _drifted(tmp_path, mutate) -> OpenAPI:
    spec = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8"))
    mutate(spec["components"]["schemas"])
    path = tmp_path / "commerce.drifted.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return OpenAPI.from_file_path(str(path), config=_config())


def test_a_newly_required_field_fails_validation(api, tmp_path):
    """A response missing a field the contract now requires must not conform."""

    def require_new_field(schemas):
        order = schemas["OrderResponse"]
        order["required"] = [*order.get("required", []), "fieldAddedByABreakingChange"]

    resp = api.post("/orders", json=_order_body(), headers=_AUTH)
    with pytest.raises(Exception):  # noqa: B017 - any openapi-core validation error is a pass here
        assert_conforms(_drifted(tmp_path, require_new_field), "post", "/orders", resp)


def test_a_null_the_contract_does_not_allow_fails_validation(api, tmp_path):
    """Dropping the ``null`` branch of a member the service sends as ``null`` must not conform."""

    def forbid_null_voucher(schemas):
        voucher = schemas["OrderResponse"]["properties"]["voucher"]
        voucher["anyOf"] = voucher["anyOf"][:1]

    resp = api.post("/orders", json=_order_body(), headers=_AUTH)
    assert resp.json()["voucher"] is None
    with pytest.raises(Exception):  # noqa: B017 - any openapi-core validation error is a pass here
        assert_conforms(_drifted(tmp_path, forbid_null_voucher), "post", "/orders", resp)


def test_a_drifted_enum_fails_validation(api, tmp_path):
    """Renaming an enum value the service emits must not conform."""

    def rename_pending(schemas):
        status = schemas["OrderResponse"]["properties"]["status"]
        status["enum"] = [value for value in status["enum"] if value != "pending"] + ["awaiting"]

    resp = api.post("/orders", json=_order_body(), headers=_AUTH)
    with pytest.raises(Exception):  # noqa: B017 - any openapi-core validation error is a pass here
        assert_conforms(_drifted(tmp_path, rename_pending), "post", "/orders", resp)
