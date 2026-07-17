"""COM-203: OXXO voucher payment flow — async confirmation, order stays pending.

Exercises the whole voucher seam without a real processor: the ``Order`` aggregate's
:meth:`attach_voucher` (which sets a ``pending`` payment but does *not* confirm the order), the
:class:`FakePaymentProvider`'s :meth:`create_voucher`, the create-order use case issuing a voucher
through the :class:`PaymentProvider` port instead of charging, the ``POST /orders`` route (via
dependency overrides), a SQL round-trip proving the voucher fields persist, and the response
projection. Unlike a card charge (COM-202), OXXO leaves the order ``pending`` until an asynchronous
webhook confirms the cash payment settled (COM-206).
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
from app.domain.payment import PaymentStatus, PaymentVoucherRequest
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


# --------------------------------------------------------------------------- domain: attach_voucher


def test_attach_voucher_leaves_order_pending_and_records_reference():
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)

    order.attach_voucher(
        provider="fake",
        reference="oxxo_abc123",
        expires_at=expires,
        barcode_url="https://vouchers.example/oxxo_abc123.png",
    )

    # The order is NOT confirmed — it stays pending until a webhook settles the cash payment.
    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_voucher_reference == "oxxo_abc123"
    assert order.payment_voucher_expires_at == expires
    assert order.payment_voucher_barcode_url == "https://vouchers.example/oxxo_abc123.png"


def test_attach_voucher_barcode_is_optional():
    order = _pending_order()

    order.attach_voucher(
        provider="fake", reference="oxxo_nobarcode", expires_at=datetime(2026, 7, 20, tzinfo=UTC)
    )

    assert order.payment_voucher_barcode_url is None
    assert order.payment_status is PaymentStatus.PENDING


def test_attach_voucher_on_non_pending_order_is_rejected():
    order = _pending_order()
    order.confirm()  # already moved out of pending

    with pytest.raises(IllegalOrderTransitionError):
        order.attach_voucher(
            provider="fake", reference="oxxo_x", expires_at=datetime(2026, 7, 20, tzinfo=UTC)
        )


def test_attach_voucher_twice_is_rejected():
    order = _pending_order()
    order.attach_voucher(
        provider="fake", reference="oxxo_first", expires_at=datetime(2026, 7, 20, tzinfo=UTC)
    )

    # Still pending, but a payment is already on file — a second voucher must not overwrite it.
    with pytest.raises(IllegalOrderTransitionError):
        order.attach_voucher(
            provider="fake", reference="oxxo_second", expires_at=datetime(2026, 7, 21, tzinfo=UTC)
        )
    assert order.payment_voucher_reference == "oxxo_first"


# --------------------------------------------------------------------------- fake: create_voucher


def test_fake_create_voucher_records_and_returns_reference():
    payments = FakePaymentProvider()
    request = PaymentVoucherRequest(amount=Money(Decimal("85.00")), reference="order-1")

    voucher = payments.create_voucher(request)

    assert payments.vouchers == [request]
    assert voucher.provider == "fake"
    assert voucher.reference.startswith("oxxo_")
    assert voucher.amount == Money(Decimal("85.00"))
    assert voucher.status is PaymentStatus.PENDING
    assert voucher.barcode_url and voucher.reference in voucher.barcode_url
    assert voucher.expires_at > datetime.now(UTC)


# --------------------------------------------------------------------------- use case: issuing


def test_oxxo_issues_voucher_and_leaves_order_pending():
    service, repo, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.OXXO, payment_token="tok_oxxo"),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert order.payment_provider == "fake"
    assert order.payment_voucher_reference and order.payment_voucher_reference.startswith("oxxo_")
    assert order.payment_voucher_expires_at is not None
    assert order.id in repo.orders
    # A voucher was issued, not a charge: nothing was charged.
    assert payments.charges == []
    assert len(payments.vouchers) == 1


def test_oxxo_voucher_request_uses_order_total_and_reference():
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.OXXO, payment_token="tok_oxxo"),
        bearer_token=TOKEN,
    )

    assert len(payments.vouchers) == 1
    request = payments.vouchers[0]
    # dark_kitchen: subtotal 50 (10 + 40) + delivery fee 35 = 85.00.
    assert request.amount == Money(Decimal("85.00"))
    assert request.amount == order.total
    assert request.reference == str(order.id)


def test_oxxo_without_token_still_issues_voucher():
    # Unlike a card, a voucher has nothing to charge, so no token is required to issue one.
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.OXXO, payment_token=None),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is PaymentStatus.PENDING
    assert len(payments.vouchers) == 1


def test_oxxo_forwards_idempotency_key_to_voucher():
    service, _, payments = _service()

    service.create(
        _command(payment_method_type=PaymentMethodType.OXXO, payment_token="tok_oxxo"),
        bearer_token=TOKEN,
        idempotency_key="idem-oxxo-1",
    )

    assert payments.vouchers[0].idempotency_key == "idem-oxxo-1"


# --------------------------------------------------------------------------- API: POST /orders

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


def test_create_with_oxxo_returns_201_pending_with_voucher():
    client, _, payments = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "oxxo", "token": "tok_oxxo"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    # The voucher block is projected so the client can display the payment reference (COM-609).
    voucher = payload["voucher"]
    assert voucher is not None
    assert voucher["reference"].startswith("oxxo_")
    assert voucher["amount"]["amount"] == 85.0
    assert voucher["expiresAt"]
    assert voucher["barcodeUrl"]
    assert voucher["provider"] == "fake"
    # No charge was made — settlement happens asynchronously (COM-206).
    assert payments.charges == []


def test_create_with_card_has_no_voucher_block():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": "tok_visa"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    assert response.json()["voucher"] is None


# --------------------------------------------------------------------------- persistence round-trip


def test_voucher_order_round_trips_through_sql_repository(order_repo):
    order = _pending_order()
    expires = datetime(2026, 7, 20, tzinfo=UTC)
    order.attach_voucher(
        provider="fake",
        reference="oxxo_persist_1",
        expires_at=expires,
        barcode_url="https://vouchers.example/oxxo_persist_1.png",
    )

    order_repo.add(order)
    loaded = order_repo.get(order.id, user_id=order.user_id)

    assert loaded is not None
    assert loaded.status is OrderStatus.PENDING
    assert loaded.payment_status is PaymentStatus.PENDING
    assert loaded.payment_provider == "fake"
    assert loaded.payment_voucher_reference == "oxxo_persist_1"
    # SQLite returns the DateTime naive (drops tz); Postgres preserves UTC. Compare the instant.
    loaded_expiry = loaded.payment_voucher_expires_at
    assert loaded_expiry is not None
    if loaded_expiry.tzinfo is None:
        loaded_expiry = loaded_expiry.replace(tzinfo=UTC)
    assert loaded_expiry == expires
    assert loaded.payment_voucher_barcode_url == "https://vouchers.example/oxxo_persist_1.png"


# --------------------------------------------------------------------------- projection


def test_order_response_projects_voucher_block():
    order = _pending_order()
    order.attach_voucher(
        provider="fake", reference="oxxo_proj", expires_at=datetime(2026, 7, 20, tzinfo=UTC)
    )

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert set(dumped["voucher"]) == {
        "reference",
        "amount",
        "expiresAt",
        "provider",
        "barcodeUrl",
    }
    assert dumped["voucher"]["reference"] == "oxxo_proj"


def test_order_response_voucher_is_null_without_voucher():
    order = _pending_order()

    dumped = OrderResponse.from_order(order).model_dump(by_alias=True)

    assert dumped["voucher"] is None
