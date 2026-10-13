"""COM-205: PayPal payment flow — redirect approval, async confirmation, order stays pending.

Exercises the whole approval seam without a real processor: the ``Order`` aggregate's
:meth:`attach_approval` (which sets a ``pending`` payment but does *not* confirm the order), the
:class:`FakePaymentProvider`'s :meth:`create_approval`, the create-order use case creating an
approval order through the :class:`PaymentProvider` port instead of charging, the ``POST /orders``
route (via dependency overrides), a SQL round-trip proving the approval fields persist, and the
response projection. Unlike a card charge (COM-202), PayPal leaves the order ``pending`` until an
asynchronous webhook confirms the captured payment (COM-206).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_create_order_service, get_token_verifier
from app.api.schemas import OrderResponse
from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import IllegalOrderTransitionError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.money import Money
from app.domain.order import Order
from app.domain.payment import PaymentApprovalRequest, PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.conekta import ConektaPaymentProvider
from app.payments.fake import FakePaymentProvider
from app.payments.stripe import StripePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    StubVerifier,
    make_test_pricer,
)

USER_ID = uuid.uuid4()
PLAN_ID = str(uuid.uuid4())
TOKEN = "caller-token"

# A non-real, non-key-shaped sentinel for the live adapters, which raise before using it.
PROVIDER_SECRET = "fake-provider-secret-not-a-real-key"  # gitleaks:allow


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None),
        ],
    )


def _command(**overrides) -> CreateOrderCommand:
    base = dict(
        user_id=USER_ID,
        meal_plan_id=PLAN_ID,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id=None,
        notes=None,
        payment_method_type=None,
        payment_token=None,
    )
    base.update(overrides)
    return CreateOrderCommand(**base)


def _service() -> tuple[CreateOrderService, InMemoryOrderRepository, FakePaymentProvider]:
    repo = InMemoryOrderRepository()
    payments = FakePaymentProvider()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        payments,
        InMemoryIdempotencyStore(),
    )
    return service, repo, payments


def _pending_order() -> Order:
    return Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.PICKUP,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
    )


# ------------------------------------------------------------------------- domain: attach_approval


def test_attach_approval_leaves_order_pending_and_records_url():
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)

    order.attach_approval(
        provider="fake",
        reference="paypal_abc123",
        approval_url="https://paypal.example/checkout/paypal_abc123",
        expires_at=expires,
    )

    # The order is NOT confirmed — it stays pending until a webhook settles the payment.
    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_approval_reference == "paypal_abc123"
    assert order.payment_approval_url == "https://paypal.example/checkout/paypal_abc123"
    assert order.payment_approval_expires_at == expires


def test_attach_approval_on_non_pending_order_is_rejected():
    order = _pending_order()
    order.confirm()  # already moved out of pending

    with pytest.raises(IllegalOrderTransitionError):
        order.attach_approval(
            provider="fake",
            reference="paypal_x",
            approval_url="https://paypal.example/checkout/paypal_x",
            expires_at=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_attach_approval_twice_is_rejected():
    order = _pending_order()
    order.attach_approval(
        provider="fake",
        reference="paypal_first",
        approval_url="https://paypal.example/checkout/paypal_first",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    # Still pending, but a payment is already on file — a second approval must not overwrite it.
    with pytest.raises(IllegalOrderTransitionError):
        order.attach_approval(
            provider="fake",
            reference="paypal_second",
            approval_url="https://paypal.example/checkout/paypal_second",
            expires_at=datetime(2026, 7, 21, tzinfo=UTC),
        )
    assert order.payment_approval_reference == "paypal_first"


# ------------------------------------------------------------------------- fake: create_approval


def test_fake_create_approval_records_and_returns_url():
    payments = FakePaymentProvider()
    request = PaymentApprovalRequest(amount=Money(Decimal("85.00")), reference="order-1")

    approval = payments.create_approval(request)

    assert payments.approvals == [request]
    assert approval.provider == "fake"
    assert approval.reference.startswith("paypal_")
    assert approval.approval_url.endswith(approval.reference)
    assert approval.approval_url.startswith("https://")
    assert approval.amount == Money(Decimal("85.00"))
    assert approval.status is PaymentStatus.PENDING
    assert approval.expires_at > datetime.now(UTC)


@pytest.mark.parametrize("provider_cls", [StripePaymentProvider, ConektaPaymentProvider])
def test_live_adapters_defer_approval_creation_to_com205(provider_cls: type):
    provider = provider_cls(PROVIDER_SECRET, base_url="https://api.example.test")

    with pytest.raises(NotImplementedError, match="COM-205"):
        provider.create_approval(PaymentApprovalRequest(amount=Money(Decimal("10.00"))))


# ------------------------------------------------------------------------- use case: issuing


def test_paypal_creates_approval_and_leaves_order_pending():
    service, repo, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.PAYPAL, payment_token="tok_paypal"),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_approval_reference and order.payment_approval_reference.startswith(
        "paypal_"
    )
    assert order.payment_approval_url and order.payment_approval_url.startswith("https://")
    assert order.payment_approval_expires_at is not None
    assert order.id in repo.orders
    # An approval order was created, not a charge: nothing was charged.
    assert payments.charges == []
    assert len(payments.approvals) == 1


def test_paypal_approval_request_uses_order_total_and_reference():
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.PAYPAL, payment_token="tok_paypal"),
        bearer_token=TOKEN,
    )

    assert len(payments.approvals) == 1
    request = payments.approvals[0]
    # dark_kitchen: subtotal 50 (10 + 40) + delivery fee 35 = 85.00.
    assert request.amount == Money(Decimal("85.00"))
    assert request.amount == order.total
    assert request.reference == str(order.id)


def test_paypal_without_token_still_creates_approval():
    # Unlike a card, an approval has nothing to charge, so no token is required to create one.
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.PAYPAL, payment_token=None),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert len(payments.approvals) == 1


def test_paypal_forwards_idempotency_key_to_approval():
    service, _, payments = _service()

    service.create(
        _command(payment_method_type=PaymentMethodType.PAYPAL, payment_token="tok_paypal"),
        bearer_token=TOKEN,
        idempotency_key="idem-paypal-1",
    )

    assert payments.approvals[0].idempotency_key == "idem-paypal-1"


# ------------------------------------------------------------------------- API: POST /orders

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

VALID_BODY = {
    "mealPlanId": PLAN_ID,
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
}


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_create_order_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build() -> tuple[TestClient, InMemoryOrderRepository, FakePaymentProvider]:
    repo = InMemoryOrderRepository()
    payments = FakePaymentProvider()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        payments,
        InMemoryIdempotencyStore(),
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo, payments


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_with_paypal_returns_201_pending_with_approval():
    client, _, payments = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "paypal", "token": "tok_paypal"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    # The approval block is projected so the client can redirect the customer to approve (COM-205).
    approval = payload["approval"]
    assert approval is not None
    assert approval["approvalUrl"].startswith("https://")
    assert approval["reference"].startswith("paypal_")
    assert approval["amount"]["amount"] == 85.0
    assert approval["expiresAt"]
    assert approval["provider"] == "fake"
    # No charge was made — settlement happens asynchronously (COM-206).
    assert payments.charges == []


def test_create_with_paypal_has_no_voucher_or_transfer_block():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "paypal", "token": "tok_paypal"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    # PayPal creates an approval, not an OXXO voucher or SPEI transfer — both blocks stay null.
    assert response.json()["voucher"] is None
    assert response.json()["transfer"] is None


def test_create_with_card_has_no_approval_block():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": "tok_visa"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    assert response.json()["approval"] is None


# ------------------------------------------------------------------------- persistence round-trip


def test_approval_order_round_trips_through_sql_repository(order_repo):
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)
    order.attach_approval(
        provider="fake",
        reference="paypal_persist_1",
        approval_url="https://paypal.example/checkout/paypal_persist_1",
        expires_at=expires,
    )

    order_repo.add(order)
    loaded = order_repo.get(order.id, user_id=order.user_id)

    assert loaded is not None
    assert loaded.status is OrderStatus.PENDING
    assert loaded.payment_status is PaymentStatus.PENDING
    assert loaded.payment_provider == "fake"
    assert loaded.payment_approval_reference == "paypal_persist_1"
    assert loaded.payment_approval_url == "https://paypal.example/checkout/paypal_persist_1"
    # SQLite returns the DateTime naive (drops tz); Postgres preserves UTC. Compare the instant.
    loaded_expiry = loaded.payment_approval_expires_at
    assert loaded_expiry is not None
    if loaded_expiry.tzinfo is None:
        loaded_expiry = loaded_expiry.replace(tzinfo=UTC)
    assert loaded_expiry == expires


# ------------------------------------------------------------------------- projection


def test_order_response_projects_approval_block():
    order = _pending_order()
    order.attach_approval(
        provider="fake",
        reference="paypal_proj",
        approval_url="https://paypal.example/checkout/paypal_proj",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert set(dumped["approval"]) == {
        "approvalUrl",
        "reference",
        "amount",
        "expiresAt",
        "provider",
    }
    assert dumped["approval"]["approvalUrl"] == "https://paypal.example/checkout/paypal_proj"
    assert dumped["approval"]["reference"] == "paypal_proj"


def test_order_response_approval_is_null_without_approval():
    order = _pending_order()

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert dumped["approval"] is None
