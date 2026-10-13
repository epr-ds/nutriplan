"""COM-206: payment-confirmation webhook — domain, provider, service, API, and persistence.

Exercises the whole seam that settles the two asynchronous ``pending`` payment paths — OXXO vouchers
(COM-203) and SPEI transfers (COM-204) — once a signature-verified provider webhook reports the
outcome: a ``payment.confirmed`` event drives ``pending -> confirmed`` (capturing the charge id) and
a ``payment.failed`` event drives ``pending -> cancelled``. Confirmation is idempotent (a
redelivered event is a no-op that publishes nothing), and a contradictory event conflicts (409).

Everything runs offline: the ``FakePaymentProvider`` verifies an HMAC-SHA256 signature over the raw
body, and the service/API tests drive in-memory repositories via ``dependency_overrides``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_process_payment_webhook_service
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import (
    IllegalOrderTransitionError,
    OrderNotFoundError,
    WebhookVerificationError,
)
from app.domain.order import Order
from app.domain.payment import PaymentEventType, PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.conekta import ConektaPaymentProvider
from app.payments.fake import FakePaymentProvider
from app.payments.stripe import StripePaymentProvider
from tests.fakes import InMemoryOrderRepository

WEBHOOK_SECRET = "fake-webhook-secret-not-a-real-key"  # gitleaks:allow
PROVIDER_SECRET = "fake-provider-secret-not-a-real-key"  # gitleaks:allow
USER_ID = uuid.uuid4()


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _event_bytes(*, event_type: str, reference: str, charge_id: str | None = None) -> bytes:
    data: dict[str, str] = {"reference": reference}
    if charge_id is not None:
        data["charge_id"] = charge_id
    return json.dumps({"type": event_type, "data": data}).encode("utf-8")


def _address() -> Address:
    return Address(
        street="Av. Reforma 100",
        city="Ciudad de Mexico",
        state="CDMX",
        zip_code="06600",
        country="MX",
    )


def _pending_order() -> Order:
    return Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.PICKUP,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
    )


def _async_pending_order() -> Order:
    """A ``pending`` order awaiting settlement, as an issued SPEI transfer would leave it."""
    order = _pending_order()
    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_abc123",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    return order


# --------------------------------------------------------------------------------------------------
# Domain: Order.confirm_payment / Order.fail_payment (idempotent + guarded)
# --------------------------------------------------------------------------------------------------


def test_confirm_payment_confirms_pending_order_and_captures_charge():
    order = _async_pending_order()

    order.confirm_payment(charge_id="fake_ch_1")

    assert order.status is OrderStatus.CONFIRMED
    assert order.payment_status is PaymentStatus.SUCCEEDED
    assert order.payment_charge_id == "fake_ch_1"
    assert [e.to_status for e in order.pull_events()] == [OrderStatus.CONFIRMED]


def test_confirm_payment_is_idempotent_on_redelivery():
    order = _async_pending_order()
    order.confirm_payment(charge_id="fake_ch_1")
    order.pull_events()

    order.confirm_payment(charge_id="fake_ch_2")

    assert order.status is OrderStatus.CONFIRMED
    assert order.payment_charge_id == "fake_ch_1"  # the no-op left the first charge intact
    assert order.pull_events() == []


def test_confirm_payment_on_a_failed_order_conflicts():
    order = _async_pending_order()
    order.fail_payment()

    with pytest.raises(IllegalOrderTransitionError):
        order.confirm_payment()
    assert order.status is OrderStatus.CANCELLED


def test_fail_payment_cancels_pending_order():
    order = _async_pending_order()

    order.fail_payment()

    assert order.status is OrderStatus.CANCELLED
    assert order.payment_status is PaymentStatus.FAILED
    assert [e.to_status for e in order.pull_events()] == [OrderStatus.CANCELLED]


def test_fail_payment_is_idempotent_on_redelivery():
    order = _async_pending_order()
    order.fail_payment()
    order.pull_events()

    order.fail_payment()

    assert order.status is OrderStatus.CANCELLED
    assert order.pull_events() == []


def test_fail_payment_on_a_confirmed_order_conflicts():
    order = _async_pending_order()
    order.confirm_payment()

    with pytest.raises(IllegalOrderTransitionError):
        order.fail_payment()
    assert order.status is OrderStatus.CONFIRMED
    assert order.payment_status is PaymentStatus.SUCCEEDED


# --------------------------------------------------------------------------------------------------
# Provider: FakePaymentProvider.parse_webhook (verify signature + parse body)
# --------------------------------------------------------------------------------------------------


def test_parse_webhook_verifies_signature_and_parses_confirmed():
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    reference = str(uuid.uuid4())
    payload = _event_bytes(event_type="payment.confirmed", reference=reference, charge_id="ch_9")

    event = provider.parse_webhook(payload, _sign(payload))

    assert event.type is PaymentEventType.CONFIRMED
    assert event.reference == reference
    assert event.provider == "fake"
    assert event.charge_id == "ch_9"


def test_parse_webhook_parses_a_failed_event_without_a_charge():
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    payload = _event_bytes(event_type="payment.failed", reference=str(uuid.uuid4()))

    event = provider.parse_webhook(payload, _sign(payload))

    assert event.type is PaymentEventType.FAILED
    assert event.charge_id is None


def test_parse_webhook_rejects_a_bad_signature():
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        provider.parse_webhook(payload, "deadbeef")


def test_parse_webhook_rejects_a_tampered_body():
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    signed = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))
    signature = _sign(signed)
    tampered = _event_bytes(event_type="payment.failed", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        provider.parse_webhook(tampered, signature)


def test_parse_webhook_rejects_a_missing_signature():
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        provider.parse_webhook(payload, "")


@pytest.mark.parametrize(
    "payload",
    [
        b"this is not json",
        json.dumps({"data": {"reference": "x"}}).encode("utf-8"),  # missing type
        json.dumps({"type": "payment.zzz", "data": {"reference": "x"}}).encode("utf-8"),  # unknown
        json.dumps({"type": "payment.confirmed", "data": {}}).encode("utf-8"),  # missing reference
        json.dumps({"type": "payment.confirmed"}).encode("utf-8"),  # missing data
    ],
)
def test_parse_webhook_rejects_a_correctly_signed_but_malformed_body(payload: bytes):
    provider = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)

    with pytest.raises(WebhookVerificationError):
        provider.parse_webhook(payload, _sign(payload))


@pytest.mark.parametrize("provider_cls", [StripePaymentProvider, ConektaPaymentProvider])
def test_live_adapters_defer_webhook_verification_to_com206(provider_cls: type):
    provider = provider_cls(PROVIDER_SECRET, base_url="https://api.example.test")

    with pytest.raises(NotImplementedError, match="COM-206"):
        provider.parse_webhook(b"{}", "signature")


# --------------------------------------------------------------------------------------------------
# Application: ProcessPaymentWebhookService.process
# --------------------------------------------------------------------------------------------------


def _service_with(order: Order):
    repo = InMemoryOrderRepository()
    repo.add(order)
    payments = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    publisher = InMemoryEventPublisher()
    service = ProcessPaymentWebhookService(repo, payments, publisher)
    return service, repo, publisher


def test_process_confirms_the_referenced_order():
    order = _async_pending_order()
    service, repo, publisher = _service_with(order)
    payload = _event_bytes(
        event_type="payment.confirmed", reference=str(order.id), charge_id="ch_1"
    )

    settled = service.process(payload=payload, signature=_sign(payload))

    assert settled.status is OrderStatus.CONFIRMED
    assert settled.payment_status is PaymentStatus.SUCCEEDED
    assert settled.payment_charge_id == "ch_1"
    assert repo.orders[order.id].status is OrderStatus.CONFIRMED
    assert [type(e).__name__ for e in publisher.published] == ["OrderStatusChanged"]


def test_process_fails_the_referenced_order():
    order = _async_pending_order()
    service, repo, _ = _service_with(order)
    payload = _event_bytes(event_type="payment.failed", reference=str(order.id))

    settled = service.process(payload=payload, signature=_sign(payload))

    assert settled.status is OrderStatus.CANCELLED
    assert settled.payment_status is PaymentStatus.FAILED
    assert repo.orders[order.id].status is OrderStatus.CANCELLED


def test_process_is_idempotent_and_publishes_once():
    order = _async_pending_order()
    service, repo, publisher = _service_with(order)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(order.id))
    signature = _sign(payload)

    service.process(payload=payload, signature=signature)
    service.process(payload=payload, signature=signature)  # redelivery

    assert repo.orders[order.id].status is OrderStatus.CONFIRMED
    assert len(publisher.published) == 1  # the redelivery recorded and published nothing


def test_process_rejects_a_bad_signature():
    service, _, _ = _service_with(_async_pending_order())
    payload = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))

    with pytest.raises(WebhookVerificationError):
        service.process(payload=payload, signature="not-the-right-signature")


def test_process_for_an_unknown_order_is_not_found():
    service, _, _ = _service_with(_async_pending_order())
    payload = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))

    with pytest.raises(OrderNotFoundError):
        service.process(payload=payload, signature=_sign(payload))


def test_process_with_a_non_uuid_reference_is_not_found():
    service, _, _ = _service_with(_async_pending_order())
    payload = _event_bytes(event_type="payment.confirmed", reference="not-a-uuid")

    with pytest.raises(OrderNotFoundError):
        service.process(payload=payload, signature=_sign(payload))


def test_process_conflicting_event_raises():
    order = _async_pending_order()
    service, _, _ = _service_with(order)
    confirm = _event_bytes(event_type="payment.confirmed", reference=str(order.id))
    service.process(payload=confirm, signature=_sign(confirm))

    fail = _event_bytes(event_type="payment.failed", reference=str(order.id))
    with pytest.raises(IllegalOrderTransitionError):
        service.process(payload=fail, signature=_sign(fail))


# --------------------------------------------------------------------------------------------------
# API: POST /webhooks/payments
# --------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_process_payment_webhook_service, None)


def _client_for(order: Order) -> tuple[TestClient, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    repo.add(order)
    payments = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    publisher = InMemoryEventPublisher()
    app.dependency_overrides[get_process_payment_webhook_service] = lambda: (
        ProcessPaymentWebhookService(repo, payments, publisher)
    )
    return TestClient(app), repo


def test_webhook_confirms_order_and_returns_200():
    order = _async_pending_order()
    client, repo = _client_for(order)
    payload = _event_bytes(
        event_type="payment.confirmed", reference=str(order.id), charge_id="ch_1"
    )

    response = client.post(
        "/webhooks/payments",
        content=payload,
        headers={"X-Webhook-Signature": _sign(payload)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["orderId"] == str(order.id)
    assert body["status"] == "confirmed"
    assert repo.orders[order.id].status is OrderStatus.CONFIRMED


def test_webhook_failed_event_cancels_order():
    order = _async_pending_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="payment.failed", reference=str(order.id))

    response = client.post(
        "/webhooks/payments",
        content=payload,
        headers={"X-Webhook-Signature": _sign(payload)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert repo.orders[order.id].status is OrderStatus.CANCELLED


def test_webhook_ignores_a_bearer_token_and_authenticates_by_signature():
    order = _async_pending_order()
    client, _ = _client_for(order)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(order.id))

    response = client.post(
        "/webhooks/payments",
        content=payload,
        headers={
            "X-Webhook-Signature": _sign(payload),
            "Authorization": "Bearer this-is-ignored",
        },
    )

    assert response.status_code == 200


def test_webhook_with_a_bad_signature_returns_400_and_leaves_order_pending():
    order = _async_pending_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(order.id))

    response = client.post(
        "/webhooks/payments",
        content=payload,
        headers={"X-Webhook-Signature": "deadbeef"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert repo.orders[order.id].status is OrderStatus.PENDING


def test_webhook_without_a_signature_returns_400():
    order = _async_pending_order()
    client, _ = _client_for(order)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(order.id))

    response = client.post("/webhooks/payments", content=payload)

    assert response.status_code == 400


def test_webhook_for_an_unknown_order_returns_404():
    client, _ = _client_for(_async_pending_order())
    payload = _event_bytes(event_type="payment.confirmed", reference=str(uuid.uuid4()))

    response = client.post(
        "/webhooks/payments",
        content=payload,
        headers={"X-Webhook-Signature": _sign(payload)},
    )

    assert response.status_code == 404


def test_webhook_conflicting_event_returns_409():
    order = _async_pending_order()
    client, _ = _client_for(order)
    confirm = _event_bytes(event_type="payment.confirmed", reference=str(order.id))
    client.post(
        "/webhooks/payments",
        content=confirm,
        headers={"X-Webhook-Signature": _sign(confirm)},
    )

    fail = _event_bytes(event_type="payment.failed", reference=str(order.id))
    response = client.post(
        "/webhooks/payments",
        content=fail,
        headers={"X-Webhook-Signature": _sign(fail)},
    )

    assert response.status_code == 409


def test_webhook_redelivery_is_idempotent_and_returns_200():
    order = _async_pending_order()
    client, repo = _client_for(order)
    payload = _event_bytes(event_type="payment.confirmed", reference=str(order.id))
    headers = {"X-Webhook-Signature": _sign(payload)}

    first = client.post("/webhooks/payments", content=payload, headers=headers)
    second = client.post("/webhooks/payments", content=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "confirmed"
    assert repo.orders[order.id].status is OrderStatus.CONFIRMED


# --------------------------------------------------------------------------------------------------
# Persistence: the settlement survives a SQL round-trip through update()
# --------------------------------------------------------------------------------------------------


def test_confirm_payment_persists_through_the_sql_repository(order_repo):
    order = _async_pending_order()
    order_repo.add(order)

    loaded = order_repo.get_by_id(order.id)
    assert loaded is not None
    loaded.confirm_payment(charge_id="fake_ch_persist")
    order_repo.update(loaded)

    reloaded = order_repo.get_by_id(order.id)
    assert reloaded is not None
    assert reloaded.status is OrderStatus.CONFIRMED
    assert reloaded.payment_status is PaymentStatus.SUCCEEDED
    assert reloaded.payment_charge_id == "fake_ch_persist"


def test_fail_payment_persists_through_the_sql_repository(order_repo):
    order = _async_pending_order()
    order_repo.add(order)

    loaded = order_repo.get_by_id(order.id)
    assert loaded is not None
    loaded.fail_payment()
    order_repo.update(loaded)

    reloaded = order_repo.get_by_id(order.id)
    assert reloaded is not None
    assert reloaded.status is OrderStatus.CANCELLED
    assert reloaded.payment_status is PaymentStatus.FAILED


def test_get_by_id_is_not_owner_scoped(order_repo):
    order = _async_pending_order()
    order_repo.add(order)

    # The owner-scoped read cannot find it for a different user, but the webhook loader can:
    # a webhook is authenticated by signature, not by a user token.
    assert order_repo.get(order.id, user_id=uuid.uuid4()) is None
    found = order_repo.get_by_id(order.id)
    assert found is not None
    assert found.id == order.id
