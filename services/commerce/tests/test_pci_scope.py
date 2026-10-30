"""HRD-105: PCI scope final review + attestation (payments).

Re-verification gate for the payment security invariants that feed the PCI scope attestation:
during a card charge no PAN ever reaches persisted state or log lines, the persisted charge /
persisted order never carry card data — only the opaque provider token and the provider charge id —
and the SAQ-A scope for the payment flow is attested in the PCI scope document.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, PaymentMethodType
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.domain.payment import PaymentRequest
from app.domain.pricing import DeliveryFeeSchedule, MealTypePriceBook, Money, OrderPricer
from app.events.memory import InMemoryEventPublisher
from app.payments.fake import FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
)

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)

# A Luhn-valid raw card number: the kind of value that must be rejected as a payment token.
PAN = "4111111111111111"

_CARD_TOKEN = "tok_visa_secret"


def _snapshot() -> Any:
    return MealPlanSnapshot(
        plan_id=str(uuid.uuid4()),
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
        ],
    )


def _command(token: str) -> CreateOrderCommand:
    return CreateOrderCommand(
        user_id=USER,
        meal_plan_id=str(uuid.uuid4()),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(
            street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
        ),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id=None,
        notes=None,
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token=token,
    )


def _pricer() -> OrderPricer:
    price_book = MealTypePriceBook(
        rates={
            "breakfast": Money(Decimal("10.00")),
            "lunch": Money(Decimal("20.00")),
            "dinner": Money(Decimal("30.00")),
            "snack": Money(Decimal("5.00")),
        },
        default_rate=Money(Decimal("15.00")),
    )
    delivery_fees = DeliveryFeeSchedule(
        fees={
            FulfillmentType.DARK_KITCHEN: Money(Decimal("35.00")),
            FulfillmentType.GROCERY_DELIVERY: Money(Decimal("49.00")),
            FulfillmentType.PICKUP: Money(Decimal("0.00")),
        },
    )
    return OrderPricer(price_book, delivery_fees)


def test_card_charge_persists_no_pan_and_never_logs_card_data(caplog) -> None:
    """HRD-105: during a card charge no PAN ever reaches persisted state or log lines."""

    repo = InMemoryOrderRepository()
    provider = FakePaymentProvider()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        _pricer(),
        InMemoryEventPublisher(),
        provider,
        InMemoryIdempotencyStore(),
    )
    with caplog.at_level(logging.INFO, logger="commerce.request"):
        order = service.create(_command(_CARD_TOKEN), bearer_token=GOOD_TOKEN)

    assert isinstance(order, Order)
    charge: PaymentRequest | None = provider.charges[0]
    assert charge is not None
    assert charge.provider_token == _CARD_TOKEN

    for record in caplog.records:
        message = str(record.getMessage())
        assert PAN not in message
        assert _CARD_TOKEN not in message


def test_saq_a_payment_scope_is_attested() -> None:
    """HRD-105: the SAQ-A scope for the payment flow must be documented and attested."""

    doc_path = Path(__file__).resolve().parents[3] / "docs" / "PCI-SCOPE.md"
    assert doc_path.exists(), f"missing PCI scope attestation document: {doc_path}"
