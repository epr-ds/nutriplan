"""COM-303: kitchen status webhook — verifier, service, API, and events.

Exercises the *inbound* half of dark-kitchen fulfilment: a kitchen posts a signature-verified status
callback, and a ``kitchen.preparing`` event drives ``confirmed -> preparing`` while a
``kitchen.dispatched`` event drives ``preparing -> in_transit``. Both are idempotent (a redelivered
event is a no-op that publishes nothing), and an out-of-order report conflicts (409).

Everything runs offline: the :class:`KitchenWebhookVerifier` checks an HMAC-SHA256 signature over
the raw body, and the service/API tests drive in-memory repositories via ``dependency_overrides``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.adapters.kitchen_webhook_verifier import KitchenWebhookVerifier
from app.api.deps import get_process_kitchen_webhook_service
from app.application.process_kitchen_webhook import ProcessKitchenWebhookService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import (
    IllegalOrderTransitionError,
    OrderNotFoundError,
    WebhookVerificationError,
)
from app.domain.kitchen import KitchenEventType
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.main import app
from tests.fakes import InMemoryOrderRepository

WEBHOOK_SECRET = "fake-kitchen-secret-not-a-real-key"  # gitleaks:allow
USER_ID = uuid.uuid4()


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _event_bytes(*, event_type: str, reference: str) -> bytes:
    return json.dumps({"type": event_type, "data": {"reference": reference}}).encode("utf-8")


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _confirmed_order() -> Order:
    order = Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id="kitchen-1",
    )
    order.confirm()
    order.pull_events()
    return order


def _preparing_order() -> Order:
    order = _confirmed_order()
    order.report_preparing()
    order.pull_events()
    return order


# --------------------------------------------------------------------------------------------------
# Adapter: KitchenWebhookVerifier.parse (verify signature + parse body)
# --------------------------------------------------------------------------------------------------


def test_verifier_parses_a_preparing_event():
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    reference = str(uuid.uuid4())
    payload = _event_bytes(event_type="kitchen.preparing", reference=reference)

    event = verifier.parse(payload, _sign(payload))

    assert event.type is KitchenEventType.PREPARING
    assert event.reference == reference


def test_verifier_parses_a_dispatched_event():
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    payload = _event_bytes(event_type="kitchen.dispatched", reference=str(uuid.uuid4()))

    event = verifier.parse(payload, _sign(payload))

    assert event.type is KitchenEventType.DISPATCHED


def test_verifier_rejects_a_bad_signature():
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        verifier.parse(payload, "deadbeef")


def test_verifier_rejects_a_tampered_body():
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    signed = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))
    signature = _sign(signed)
    tampered = _event_bytes(event_type="kitchen.dispatched", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        verifier.parse(tampered, signature)


def test_verifier_rejects_a_missing_signature():
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        verifier.parse(payload, "")


@pytest.mark.parametrize(
    "payload",
    [
        b"this is not json",
        json.dumps({"data": {"reference": "x"}}).encode("utf-8"),  # missing type
        json.dumps({"type": "kitchen.zzz", "data": {"reference": "x"}}).encode("utf-8"),  # unknown
        json.dumps({"type": "kitchen.preparing", "data": {}}).encode("utf-8"),  # missing reference
        json.dumps({"type": "kitchen.preparing"}).encode("utf-8"),  # missing data
    ],
)
def test_verifier_rejects_a_correctly_signed_but_malformed_body(payload: bytes):
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)

    with pytest.raises(WebhookVerificationError):
        verifier.parse(payload, _sign(payload))


# --------------------------------------------------------------------------------------------------
# Application: ProcessKitchenWebhookService.process
# --------------------------------------------------------------------------------------------------


def _service_with(order: Order):
    repo = InMemoryOrderRepository()
    repo.add(order)
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    publisher = InMemoryEventPublisher()
    service = ProcessKitchenWebhookService(repo, verifier, publisher)
    return service, repo, publisher


def test_process_preparing_advances_the_referenced_order():
    order = _confirmed_order()
    service, repo, publisher = _service_with(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))

    advanced = service.process(payload=payload, signature=_sign(payload))

    assert advanced.status is OrderStatus.PREPARING
    assert repo.orders[order.id].status is OrderStatus.PREPARING
    assert [type(e).__name__ for e in publisher.published] == ["OrderStatusChanged"]


def test_process_dispatched_advances_a_preparing_order():
    order = _preparing_order()
    service, repo, _ = _service_with(order)
    payload = _event_bytes(event_type="kitchen.dispatched", reference=str(order.id))

    advanced = service.process(payload=payload, signature=_sign(payload))

    assert advanced.status is OrderStatus.IN_TRANSIT
    assert repo.orders[order.id].status is OrderStatus.IN_TRANSIT


def test_process_is_idempotent_and_publishes_once():
    order = _confirmed_order()
    service, repo, publisher = _service_with(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))
    signature = _sign(payload)

    service.process(payload=payload, signature=signature)
    service.process(payload=payload, signature=signature)  # redelivery

    assert repo.orders[order.id].status is OrderStatus.PREPARING
    assert len(publisher.published) == 1  # the redelivery recorded and published nothing


def test_process_rejects_a_bad_signature():
    service, _, _ = _service_with(_confirmed_order())
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        service.process(payload=payload, signature="not-the-right-signature")


def test_process_for_an_unknown_order_is_not_found():
    service, _, _ = _service_with(_confirmed_order())
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))

    with pytest.raises(OrderNotFoundError):
        service.process(payload=payload, signature=_sign(payload))


def test_process_with_a_non_uuid_reference_is_not_found():
    service, _, _ = _service_with(_confirmed_order())
    payload = _event_bytes(event_type="kitchen.preparing", reference="not-a-uuid")

    with pytest.raises(OrderNotFoundError):
        service.process(payload=payload, signature=_sign(payload))


def test_process_dispatched_before_preparing_conflicts():
    order = _confirmed_order()
    service, _, _ = _service_with(order)
    payload = _event_bytes(event_type="kitchen.dispatched", reference=str(order.id))

    with pytest.raises(IllegalOrderTransitionError):
        service.process(payload=payload, signature=_sign(payload))


# --------------------------------------------------------------------------------------------------
# API: POST /webhooks/kitchen
# --------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_process_kitchen_webhook_service, None)


def _client_for(order: Order) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    repo.add(order)
    verifier = KitchenWebhookVerifier(WEBHOOK_SECRET)
    publisher = InMemoryEventPublisher()
    app.dependency_overrides[get_process_kitchen_webhook_service] = lambda: (
        ProcessKitchenWebhookService(repo, verifier, publisher)
    )
    return TestClient(app), repo


def test_webhook_preparing_advances_order_and_returns_200():
    order = _confirmed_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))

    response = client.post(
        "/webhooks/kitchen", content=payload, headers={"X-Webhook-Signature": _sign(payload)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["orderId"] == str(order.id)
    assert body["status"] == "preparing"
    assert repo.orders[order.id].status is OrderStatus.PREPARING


def test_webhook_dispatched_advances_a_preparing_order():
    order = _preparing_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="kitchen.dispatched", reference=str(order.id))

    response = client.post(
        "/webhooks/kitchen", content=payload, headers={"X-Webhook-Signature": _sign(payload)}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_transit"
    assert repo.orders[order.id].status is OrderStatus.IN_TRANSIT


def test_webhook_ignores_a_bearer_token_and_authenticates_by_signature():
    order = _confirmed_order()
    client, _ = _client_for(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))

    response = client.post(
        "/webhooks/kitchen",
        content=payload,
        headers={"X-Webhook-Signature": _sign(payload), "Authorization": "******"},
    )

    assert response.status_code == 200


def test_webhook_with_a_bad_signature_returns_400_and_leaves_order_confirmed():
    order = _confirmed_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))

    response = client.post(
        "/webhooks/kitchen", content=payload, headers={"X-Webhook-Signature": "deadbeef"}
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert repo.orders[order.id].status is OrderStatus.CONFIRMED


def test_webhook_without_a_signature_returns_400():
    order = _confirmed_order()
    client, _ = _client_for(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))

    response = client.post("/webhooks/kitchen", content=payload)

    assert response.status_code == 400


def test_webhook_for_an_unknown_order_returns_404():
    client, _ = _client_for(_confirmed_order())
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(uuid.uuid4()))

    response = client.post(
        "/webhooks/kitchen", content=payload, headers={"X-Webhook-Signature": _sign(payload)}
    )

    assert response.status_code == 404


def test_webhook_out_of_order_report_returns_409():
    order = _confirmed_order()
    client, _ = _client_for(order)
    payload = _event_bytes(event_type="kitchen.dispatched", reference=str(order.id))

    response = client.post(
        "/webhooks/kitchen", content=payload, headers={"X-Webhook-Signature": _sign(payload)}
    )

    assert response.status_code == 409


def test_webhook_redelivery_is_idempotent_and_returns_200():
    order = _confirmed_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="kitchen.preparing", reference=str(order.id))
    headers = {"X-Webhook-Signature": _sign(payload)}

    first = client.post("/webhooks/kitchen", content=payload, headers=headers)
    second = client.post("/webhooks/kitchen", content=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "preparing"
    assert repo.orders[order.id].status is OrderStatus.PREPARING
