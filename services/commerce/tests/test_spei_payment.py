"""COM-204: SPEI bank-transfer payment flow — async confirmation, order stays pending.

Exercises the whole transfer seam without a real processor: the ``Order`` aggregate's
:meth:`attach_transfer` (which sets a ``pending`` payment but does *not* confirm the order), the
:class:`FakePaymentProvider`'s :meth:`create_transfer`, the create-order use case issuing transfer
instructions through the :class:`PaymentProvider` port instead of charging, the ``POST /orders``
route (via dependency overrides), a SQL round-trip proving the transfer fields persist, and the
response projection. Unlike a card charge (COM-202), SPEI leaves the order ``pending`` until an
asynchronous webhook confirms the transfer landed (COM-206).
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
from app.domain.payment import PaymentStatus, PaymentTransferRequest
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import FakePaymentProvider
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


# ------------------------------------------------------------------------- domain: attach_transfer


def test_attach_transfer_leaves_order_pending_and_records_clabe():
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)

    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_abc123",
        expires_at=expires,
    )

    # The order is NOT confirmed — it stays pending until a webhook settles the transfer.
    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_transfer_clabe == "012345678901234567"
    assert order.payment_transfer_reference == "spei_abc123"
    assert order.payment_transfer_expires_at == expires


def test_attach_transfer_on_non_pending_order_is_rejected():
    order = _pending_order()
    order.confirm()  # already moved out of pending

    with pytest.raises(IllegalOrderTransitionError):
        order.attach_transfer(
            provider="fake",
            clabe="012345678901234567",
            reference="spei_x",
            expires_at=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_attach_transfer_twice_is_rejected():
    order = _pending_order()
    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_first",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    # Still pending, but a payment is already on file — a second transfer must not overwrite it.
    with pytest.raises(IllegalOrderTransitionError):
        order.attach_transfer(
            provider="fake",
            clabe="765432109876543210",
            reference="spei_second",
            expires_at=datetime(2026, 7, 21, tzinfo=UTC),
        )
    assert order.payment_transfer_reference == "spei_first"


# ------------------------------------------------------------------------- fake: create_transfer


def test_fake_create_transfer_records_and_returns_clabe():
    payments = FakePaymentProvider()
    request = PaymentTransferRequest(amount=Money(Decimal("85.00")), reference="order-1")

    transfer = payments.create_transfer(request)

    assert payments.transfers == [request]
    assert transfer.provider == "fake"
    # A SPEI CLABE is exactly 18 numeric digits.
    assert transfer.clabe.isdigit() and len(transfer.clabe) == 18
    assert transfer.reference.startswith("spei_")
    assert transfer.amount == Money(Decimal("85.00"))
    assert transfer.status is PaymentStatus.PENDING
    assert transfer.expires_at > datetime.now(UTC)


# ------------------------------------------------------------------------- use case: issuing


def test_spei_issues_transfer_and_leaves_order_pending():
    service, repo, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.SPEI, payment_token="tok_spei"),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_transfer_clabe and len(order.payment_transfer_clabe) == 18
    assert order.payment_transfer_reference and order.payment_transfer_reference.startswith("spei_")
    assert order.payment_transfer_expires_at is not None
    assert order.id in repo.orders
    # Transfer instructions were issued, not a charge: nothing was charged.
    assert payments.charges == []
    assert len(payments.transfers) == 1


def test_spei_transfer_request_uses_order_total_and_reference():
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.SPEI, payment_token="tok_spei"),
        bearer_token=TOKEN,
    )

    assert len(payments.transfers) == 1
    request = payments.transfers[0]
    # dark_kitchen: subtotal 50 (10 + 40) + delivery fee 35 = 85.00.
    assert request.amount == Money(Decimal("85.00"))
    assert request.amount == order.total
    assert request.reference == str(order.id)


def test_spei_without_token_still_issues_transfer():
    # Unlike a card, a transfer has nothing to charge, so no token is required to issue one.
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.SPEI, payment_token=None),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert len(payments.transfers) == 1


def test_spei_forwards_idempotency_key_to_transfer():
    service, _, payments = _service()

    service.create(
        _command(payment_method_type=PaymentMethodType.SPEI, payment_token="tok_spei"),
        bearer_token=TOKEN,
        idempotency_key="idem-spei-1",
    )

    assert payments.transfers[0].idempotency_key == "idem-spei-1"


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


def test_create_with_spei_returns_201_pending_with_transfer():
    client, _, payments = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "spei", "token": "tok_spei"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    # The transfer block is projected so the client can display the CLABE + reference (COM-609).
    transfer = payload["transfer"]
    assert transfer is not None
    assert transfer["clabe"].isdigit() and len(transfer["clabe"]) == 18
    assert transfer["reference"].startswith("spei_")
    assert transfer["amount"]["amount"] == 85.0
    assert transfer["expiresAt"]
    assert transfer["provider"] == "fake"
    # No charge was made — settlement happens asynchronously (COM-206).
    assert payments.charges == []


def test_create_with_spei_has_no_voucher_block():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "spei", "token": "tok_spei"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    # SPEI issues a transfer, not an OXXO voucher — the voucher block stays null.
    assert response.json()["voucher"] is None


def test_create_with_card_has_no_transfer_block():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": "tok_visa"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    assert response.json()["transfer"] is None


# ------------------------------------------------------------------------- persistence round-trip


def test_transfer_order_round_trips_through_sql_repository(order_repo):
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)
    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_persist_1",
        expires_at=expires,
    )

    order_repo.add(order)
    loaded = order_repo.get(order.id, user_id=order.user_id)

    assert loaded is not None
    assert loaded.status is OrderStatus.PENDING
    assert loaded.payment_status is PaymentStatus.PENDING
    assert loaded.payment_provider == "fake"
    assert loaded.payment_transfer_clabe == "012345678901234567"
    assert loaded.payment_transfer_reference == "spei_persist_1"
    # SQLite returns the DateTime naive (drops tz); Postgres preserves UTC. Compare the instant.
    loaded_expiry = loaded.payment_transfer_expires_at
    assert loaded_expiry is not None
    if loaded_expiry.tzinfo is None:
        loaded_expiry = loaded_expiry.replace(tzinfo=UTC)
    assert loaded_expiry == expires


# ------------------------------------------------------------------------- projection


def test_order_response_projects_transfer_block():
    order = _pending_order()
    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_proj",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert set(dumped["transfer"]) == {
        "clabe",
        "reference",
        "amount",
        "expiresAt",
        "provider",
    }
    assert dumped["transfer"]["clabe"] == "012345678901234567"
    assert dumped["transfer"]["reference"] == "spei_proj"


def test_order_response_transfer_is_null_without_transfer():
    order = _pending_order()

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert dumped["transfer"] is None
