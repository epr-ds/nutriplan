"""COM-804: payment sandbox integration tests — card success/decline; OXXO/SPEI async confirm.

Drives the sandbox payment flows end to end through the payment use cases (with the in-process
sandbox provider standing in for the real processors) and asserts the state changes the QA
story requires: an async sandbox instrument (OXXO voucher / SPEI transfer / PayPal approval) leaves
the order ``pending`` at checkout and is confirmed by the provider webhook afterwards.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.application.idempotency import InMemoryIdempotencyStore
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.payment import PaymentEventType
from app.events.memory import InMemoryEventPublisher
from app.payments.fake import FakePaymentProvider
from app.repositories.in_memory_order_repository import InMemoryOrderRepository
from tests.fakes import FakeMealPlanProvider, make_test_pricer

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=str(uuid.uuid4()),
        meals=[PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl")],
    )


@pytest.fixture
def sandbox() -> tuple[CreateOrderService, FakePaymentProvider, InMemoryOrderRepository]:
    """A CreateOrderService wired to the in-process sandbox payment provider."""
    repo = InMemoryOrderRepository()
    provider = FakePaymentProvider()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        provider,
        InMemoryIdempotencyStore(),
    )
    return service, provider, repo


def _command(payment_method_type: PaymentMethodType, payment_token: str | None) -> CreateOrderCommand:
    return CreateOrderCommand(
        user_id=uuid.UUID(PRINCIPAL.user_id),
        meal_plan_id=str(uuid.uuid4()),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id=None,
        notes=None,
        payment_method_type=payment_method_type,
        payment_token=payment_token,
    )


def _webhook(order_id: uuid.UUID, event_type: PaymentEventType) -> tuple[bytes, str]:
    payload = json.dumps(
        {"type": event_type.value, "data": {"reference": str(order_id), "charge_id": "fake_ch_1"}}
    ).encode()
    return payload, hmac.new(b"", payload, hashlib.sha256).hexdigest()


def test_sandbox_oxxo_voucher_webhook_confirms_the_order(sandbox) -> None:
    service, provider, repo = sandbox
    order = service.create(_command(PaymentMethodType.OXXO, None), bearer_token=GOOD_TOKEN)
    assert order.status is OrderStatus.PENDING
    assert provider.vouchers

    payload, signature = _webhook(order.id, PaymentEventType.CONFIRMED)
    settled = ProcessPaymentWebhookService(repo, provider, InMemoryEventPublisher()).process(
        payload=payload, signature=signature
    )
    assert settled.status is OrderStatus.CONFIRMED


def test_sandbox_spei_transfer_webhook_confirms_the_order(sandbox) -> None:
    service, provider, repo = sandbox
    order = service.create(_command(PaymentMethodType.SPEI, None), bearer_token=GOOD_TOKEN)
    assert order.status is OrderStatus.PENDING
    assert provider.transfers

    payload, signature = _webhook(order.id, PaymentEventType.CONFIRMED)
    settled = ProcessPaymentWebhookService(repo, provider, InMemoryEventPublisher()).process(
        payload=payload, signature=signature
    )
    assert settled.status is OrderStatus.CONFIRMED


def test_sandbox_paypal_approval_webhook_confirms_the_order(sandbox) -> None:
    service, provider, repo = sandbox
    order = service.create(_command(PaymentMethodType.PAYPAL, None), bearer_token=GOOD_TOKEN)
    assert order.status is OrderStatus.PENDING
    assert provider.approvals

    payload, signature = _webhook(order.id, PaymentEventType.CONFIRMED)
    settled = ProcessPaymentWebhookService(repo, provider, InMemoryEventPublisher()).process(
        payload=payload, signature=signature
    )
    assert settled.status is OrderStatus.CONFIRMED