"""COM-208: refund on cancellation (full/partial) across every layer.

Exercises the whole refund seam without a real processor: the ``Order`` aggregate's
:attr:`can_refund`/:meth:`validate_refund`/:meth:`record_refund` invariants (including the ``409``
for an unpaid order and the ``422`` for a bad amount, plus the double-refund guard), the
:class:`FakePaymentProvider`'s :meth:`refund`, the :class:`CancelOrderService` orchestration
(cancel-then-refund: a paid order is refunded in full by default or partially when an amount is
supplied, while an unpaid order is simply cancelled), the ``POST /orders/{orderId}/cancel`` route
(via dependency overrides), a SQL round-trip proving the refund fields persist, and the response
projection. The refund goes *through* the :class:`PaymentProvider` port — unlike a plain cancel.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cancel_order_service, get_token_verifier
from app.api.schemas import OrderResponse
from app.application.cancel_order import CancelOrderService
from app.application.commands import CancelOrderCommand
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, RefundStatus
from app.domain.errors import IllegalOrderTransitionError, OrderValidationError
from app.domain.money import Money
from app.domain.order import Order
from app.domain.payment import PaymentRefundRequest, PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.conekta import ConektaPaymentProvider
from app.payments.fake import FakePaymentProvider
from app.payments.stripe import StripePaymentProvider
from tests.fakes import InMemoryOrderRepository, StubVerifier

USER = uuid.uuid4()

# A non-real, non-key-shaped sentinel for the live adapters, which raise before using it.
PROVIDER_SECRET = "fake-provider-secret-not-a-real-key"  # gitleaks:allow


def _address() -> Address:
    return Address(street="s", city="c", state="st", zip_code="00000", country="MX")


def _order(*, user_id: uuid.UUID = USER, total: str = "120.00") -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        total=Money(Decimal(total)),
    )


def _paid_order(*, user_id: uuid.UUID = USER, total: str = "120.00") -> Order:
    """A confirmed order with a captured card charge — the refundable starting point (COM-202)."""
    order = _order(user_id=user_id, total=total)
    order.mark_paid(provider="fake", charge_id="fake_ch_1")
    return order


def _service(
    *orders: Order,
) -> tuple[CancelOrderService, InMemoryOrderRepository, FakePaymentProvider]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    payments = FakePaymentProvider()
    return CancelOrderService(repo, payments, InMemoryEventPublisher()), repo, payments


# ------------------------------------------------------------------------------- domain: can_refund


def test_can_refund_true_for_captured_unrefunded_payment():
    assert _paid_order().can_refund is True


def test_can_refund_false_when_unpaid():
    assert _order().can_refund is False


def test_can_refund_false_when_payment_failed():
    order = _order()
    order.payment_status = PaymentStatus.FAILED
    assert order.can_refund is False


def test_can_refund_false_without_charge_id():
    order = _order()
    order.payment_status = PaymentStatus.SUCCEEDED  # succeeded but no charge reference to act on
    assert order.can_refund is False


def test_can_refund_false_once_already_refunded():
    order = _paid_order()
    order.record_refund(refund_id="re_1", amount=Money(Decimal("120.00")))
    assert order.can_refund is False


# -------------------------------------------------------------------------- domain: validate_refund


def test_validate_refund_defaults_to_full_total():
    assert _paid_order(total="120.00").validate_refund(None) == Money(Decimal("120.00"))


def test_validate_refund_returns_requested_partial_amount():
    assert _paid_order().validate_refund(Money(Decimal("50.00"))) == Money(Decimal("50.00"))


def test_validate_refund_on_unpaid_order_conflicts():
    with pytest.raises(IllegalOrderTransitionError):
        _order().validate_refund(None)


def test_validate_refund_rejects_currency_mismatch():
    with pytest.raises(OrderValidationError):
        _paid_order().validate_refund(Money(Decimal("50.00"), "USD"))


@pytest.mark.parametrize("amount", ["0.00", "-5.00"])
def test_validate_refund_rejects_non_positive_amount(amount: str):
    with pytest.raises(OrderValidationError):
        _paid_order().validate_refund(Money(Decimal(amount)))


def test_validate_refund_rejects_amount_over_total():
    with pytest.raises(OrderValidationError):
        _paid_order(total="120.00").validate_refund(Money(Decimal("120.01")))


# ---------------------------------------------------------------------------- domain: record_refund


def test_record_refund_full_sets_status_full():
    order = _paid_order(total="120.00")
    order.record_refund(refund_id="re_1", amount=Money(Decimal("120.00")))

    assert order.refund_status is RefundStatus.FULL
    assert order.refunded_amount == Money(Decimal("120.00"))
    assert order.payment_refund_id == "re_1"


def test_record_refund_partial_sets_status_partial():
    order = _paid_order(total="120.00")
    order.record_refund(refund_id="re_2", amount=Money(Decimal("40.00")))

    assert order.refund_status is RefundStatus.PARTIAL
    assert order.refunded_amount == Money(Decimal("40.00"))


def test_record_refund_twice_is_rejected():
    order = _paid_order()
    order.record_refund(refund_id="re_1", amount=Money(Decimal("120.00")))

    # A second refund must be refused — the guard sees a refund already on file.
    with pytest.raises(IllegalOrderTransitionError):
        order.record_refund(refund_id="re_2", amount=Money(Decimal("10.00")))
    assert order.payment_refund_id == "re_1"


def test_record_refund_does_not_change_lifecycle_state():
    order = _paid_order()  # confirmed
    order.record_refund(refund_id="re_1", amount=Money(Decimal("120.00")))
    # Recording a refund is orthogonal to the lifecycle — the caller cancels separately.
    assert order.status is OrderStatus.CONFIRMED


# ------------------------------------------------------------------------------------- fake: refund


def test_fake_refund_records_and_echoes_amount():
    payments = FakePaymentProvider()
    request = PaymentRefundRequest(
        charge_id="fake_ch_1", amount=Money(Decimal("50.00")), reference="order-1"
    )

    refund = payments.refund(request)

    assert payments.refunds == [request]
    assert refund.provider == "fake"
    assert refund.refund_id.startswith("fake_re_")
    assert refund.amount == Money(Decimal("50.00"))
    assert refund.status is PaymentStatus.SUCCEEDED
    assert refund.is_success is True


@pytest.mark.parametrize("provider_cls", [StripePaymentProvider, ConektaPaymentProvider])
def test_live_adapters_defer_refund_to_live_charging(provider_cls: type):
    provider = provider_cls(PROVIDER_SECRET, base_url="https://api.example.test")

    with pytest.raises(NotImplementedError, match="COM-202"):
        provider.refund(PaymentRefundRequest(charge_id="ch_1", amount=Money(Decimal("10.00"))))


# -------------------------------------------------------------------------- use case: cancel+refund


def test_cancel_paid_order_refunds_in_full():
    order = _paid_order(total="120.00")
    service, _, payments = _service(order)

    result = service.cancel(CancelOrderCommand(user_id=USER, order_id=order.id))

    assert result.status is OrderStatus.CANCELLED
    assert result.refund_status is RefundStatus.FULL
    assert result.refunded_amount == Money(Decimal("120.00"))
    assert result.payment_refund_id and result.payment_refund_id.startswith("fake_re_")
    # The money was returned through the provider port, keyed by the captured charge + order id.
    assert len(payments.refunds) == 1
    assert payments.refunds[0].charge_id == "fake_ch_1"
    assert payments.refunds[0].amount == Money(Decimal("120.00"))
    assert payments.refunds[0].reference == str(order.id)


def test_cancel_paid_order_with_amount_refunds_partially():
    order = _paid_order(total="120.00")
    service, _, payments = _service(order)

    result = service.cancel(
        CancelOrderCommand(user_id=USER, order_id=order.id, refund_amount=Decimal("50.00"))
    )

    assert result.status is OrderStatus.CANCELLED
    assert result.refund_status is RefundStatus.PARTIAL
    assert result.refunded_amount == Money(Decimal("50.00"))
    assert payments.refunds[0].amount == Money(Decimal("50.00"))


def test_cancel_unpaid_order_does_not_refund():
    order = _order()
    service, _, payments = _service(order)

    result = service.cancel(CancelOrderCommand(user_id=USER, order_id=order.id))

    assert result.status is OrderStatus.CANCELLED
    assert result.refund_status is None
    assert result.refunded_amount is None
    assert payments.refunds == []  # nothing captured, nothing returned


def test_cancel_unpaid_order_with_amount_conflicts_and_does_not_refund():
    order = _order()
    service, _, payments = _service(order)

    # Asking to refund an order that was never paid is a conflict, not a silent no-op.
    with pytest.raises(IllegalOrderTransitionError):
        service.cancel(
            CancelOrderCommand(user_id=USER, order_id=order.id, refund_amount=Decimal("10.00"))
        )
    assert payments.refunds == []


def test_cancel_paid_order_with_excessive_amount_is_unprocessable():
    order = _paid_order(total="120.00")
    service, _, payments = _service(order)

    with pytest.raises(OrderValidationError):
        service.cancel(
            CancelOrderCommand(user_id=USER, order_id=order.id, refund_amount=Decimal("200.00"))
        )
    assert payments.refunds == []  # rejected before the provider is ever called


# ------------------------------------------------------------------- API: POST /orders/{id}/cancel

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(USER), email="a@b.com")


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_cancel_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*orders: Order) -> tuple[TestClient, InMemoryOrderRepository, FakePaymentProvider]:
    repo = InMemoryOrderRepository()
    for order in orders:
        repo.add(order)
    payments = FakePaymentProvider()
    app.dependency_overrides[get_cancel_order_service] = lambda: CancelOrderService(
        repo, payments, InMemoryEventPublisher()
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo, payments


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {GOOD_TOKEN}"}


def test_cancel_paid_order_returns_200_with_full_refund_block():
    order = _paid_order(total="120.00")
    client, _, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", headers=_auth())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"
    refund = payload["refund"]
    assert refund is not None
    assert refund["status"] == "full"
    assert refund["amount"]["amount"] == 120.0
    assert refund["refundId"].startswith("fake_re_")
    assert refund["provider"] == "fake"


def test_cancel_paid_order_with_body_returns_partial_refund():
    order = _paid_order(total="120.00")
    client, _, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", json={"refundAmount": 50}, headers=_auth())

    assert response.status_code == 200
    refund = response.json()["refund"]
    assert refund["status"] == "partial"
    assert refund["amount"]["amount"] == 50.0


def test_cancel_unpaid_order_returns_200_without_refund_block():
    order = _order()
    client, _, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", headers=_auth())

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["refund"] is None


def test_cancel_unpaid_order_with_amount_returns_409():
    order = _order()
    client, _, _ = _build(order)

    response = client.post(f"/orders/{order.id}/cancel", json={"refundAmount": 10}, headers=_auth())

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


def test_cancel_with_amount_over_total_returns_422():
    order = _paid_order(total="120.00")
    client, _, _ = _build(order)

    response = client.post(
        f"/orders/{order.id}/cancel", json={"refundAmount": 200}, headers=_auth()
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


# ------------------------------------------------------------------------- persistence round-trip


def test_refund_fields_round_trip_through_sql_repository(order_repo):
    order = _paid_order(total="120.00")
    order_repo.add(order)
    order.cancel()
    order.record_refund(refund_id="fake_re_persist", amount=Money(Decimal("40.00")))

    order_repo.update(order)
    loaded = order_repo.get(order.id, user_id=order.user_id)

    assert loaded is not None
    assert loaded.status is OrderStatus.CANCELLED
    assert loaded.payment_refund_id == "fake_re_persist"
    assert loaded.refund_status is RefundStatus.PARTIAL
    assert loaded.refunded_amount == Money(Decimal("40.00"))


# ------------------------------------------------------------------------------------- projection


def test_order_response_projects_refund_block():
    order = _paid_order(total="120.00")
    order.cancel()
    order.record_refund(refund_id="fake_re_proj", amount=Money(Decimal("120.00")))

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert set(dumped["refund"]) == {"refundId", "status", "amount", "provider"}
    assert dumped["refund"]["refundId"] == "fake_re_proj"
    assert dumped["refund"]["status"] == "full"
    assert dumped["refund"]["amount"]["amount"] == 120.0


def test_order_response_refund_is_null_without_refund():
    dumped = OrderResponse.from_order(_paid_order()).model_dump(by_alias=True)
    assert dumped["refund"] is None
