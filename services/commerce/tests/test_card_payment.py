"""COM-202: card tokenization & charge at checkout — no PAN stored, outcome mapped to order state.

Exercises the whole seam without a real processor: the ``Order`` aggregate's :meth:`mark_paid`, the
create-order use case charging the priced total through the :class:`PaymentProvider` port (a
:class:`FakePaymentProvider`), the ``POST /orders`` route (via dependency overrides), and a SQL
round-trip proving the charge reference persists. The three acceptance criteria are pinned here:

* the charge uses only the provider *token* from ``PaymentMethodRequest`` — no card data reaches us;
* a card is charged inline (``credit_card``/``debit_card``); other methods stay ``pending``;
* success confirms the order, a decline is a ``402`` and leaves no order behind.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_create_order_service, get_token_verifier
from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import (
    IllegalOrderTransitionError,
    OrderValidationError,
    PaymentDeclinedError,
)
from app.domain.events import OrderStatusChanged
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.money import Money
from app.domain.order import Order
from app.domain.payment import PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import DECLINE_TOKEN_PREFIX, FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryOrderRepository,
    StubVerifier,
    make_test_pricer,
)

USER_ID = uuid.uuid4()
PLAN_ID = str(uuid.uuid4())
TOKEN = "caller-token"
CARD_TOKEN = "tok_visa"


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
    )
    return service, repo, payments


# --------------------------------------------------------------------------- domain: mark_paid


def _pending_order() -> Order:
    return Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.PICKUP,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
    )


def test_mark_paid_records_reference_and_confirms():
    order = _pending_order()

    order.mark_paid(provider="stripe", charge_id="ch_1")

    assert order.status is OrderStatus.CONFIRMED
    assert order.payment_status is PaymentStatus.SUCCEEDED
    assert order.payment_provider == "stripe"
    assert order.payment_charge_id == "ch_1"
    # Confirming as part of payment still records the lifecycle event for the bus (COM-109).
    assert any(isinstance(event, OrderStatusChanged) for event in order.pull_events())


def test_mark_paid_on_non_pending_order_is_rejected():
    order = _pending_order()
    order.confirm()  # already moved out of pending

    with pytest.raises(IllegalOrderTransitionError):
        order.mark_paid(provider="stripe", charge_id="ch_2")


# --------------------------------------------------------------------------- use case: charging


def test_card_charge_confirms_order_and_records_reference():
    service, repo, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token=CARD_TOKEN),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.CONFIRMED
    assert order.payment_status is PaymentStatus.SUCCEEDED
    assert order.payment_provider == "fake"
    assert order.payment_charge_id and order.payment_charge_id.startswith("fake_ch_")
    assert order.id in repo.orders


def test_charge_uses_order_total_and_only_the_token():
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.DEBIT_CARD, payment_token=CARD_TOKEN),
        bearer_token=TOKEN,
    )

    assert len(payments.charges) == 1
    charge = payments.charges[0]
    # dark_kitchen: subtotal 50 (10 + 40) + delivery fee 35 = 85.00.
    assert charge.amount == Money(Decimal("85.00"))
    assert charge.amount == order.total
    # No PAN ever reaches us: the request carries only the opaque provider token + an order ref.
    assert charge.provider_token == CARD_TOKEN
    assert charge.reference == str(order.id)


def test_declined_card_raises_402_error_and_persists_no_order():
    service, repo, payments = _service()

    with pytest.raises(PaymentDeclinedError) as excinfo:
        service.create(
            _command(
                payment_method_type=PaymentMethodType.CREDIT_CARD,
                payment_token=f"{DECLINE_TOKEN_PREFIX}_1",
            ),
            bearer_token=TOKEN,
        )

    assert excinfo.value.error_code == "card_declined"
    assert repo.orders == {}  # nothing persisted on decline
    assert len(payments.charges) == 1  # the decline was actually attempted


def test_no_payment_method_leaves_order_pending_without_charging():
    service, _, payments = _service()

    order = service.create(_command(), bearer_token=TOKEN)

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is None
    assert payments.charges == []


def test_non_card_method_leaves_order_pending_without_charging():
    service, _, payments = _service()

    order = service.create(
        _command(payment_method_type=PaymentMethodType.OXXO, payment_token="tok_oxxo"),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.PENDING
    assert order.payment_status is None
    assert payments.charges == []  # async methods settle via a later webhook (COM-206)


def test_card_method_without_token_is_rejected_before_charging():
    service, repo, payments = _service()

    with pytest.raises(OrderValidationError):
        service.create(
            _command(payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token=None),
            bearer_token=TOKEN,
        )

    assert repo.orders == {}
    assert payments.charges == []


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
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo, payments


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_with_card_returns_201_confirmed():
    client, _, payments = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": CARD_TOKEN}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    assert response.json()["status"] == "confirmed"
    assert len(payments.charges) == 1


def test_create_with_declined_card_returns_402_problem_json():
    client, repo, _ = _build()
    body = {
        **VALID_BODY,
        "paymentMethod": {"type": "credit_card", "token": f"{DECLINE_TOKEN_PREFIX}_9"},
    }

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 402
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["status"] == 402
    assert problem["title"]
    assert repo.orders == {}


def test_create_with_oxxo_returns_201_pending_without_charge():
    client, _, payments = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "oxxo", "token": "tok_oxxo"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert payments.charges == []


def test_create_with_unknown_payment_type_returns_422():
    client, _, _ = _build()
    body = {**VALID_BODY, "paymentMethod": {"type": "bitcoin", "token": "tok_btc"}}

    response = client.post("/orders", json=body, headers=_auth())

    assert response.status_code == 422


# --------------------------------------------------------------------------- persistence round-trip


def test_paid_order_round_trips_through_sql_repository(order_repo):
    order = _pending_order()
    order.mark_paid(provider="stripe", charge_id="ch_persist_1")

    order_repo.add(order)
    loaded = order_repo.get(order.id, user_id=order.user_id)

    assert loaded is not None
    assert loaded.status is OrderStatus.CONFIRMED
    assert loaded.payment_status is PaymentStatus.SUCCEEDED
    assert loaded.payment_provider == "stripe"
    assert loaded.payment_charge_id == "ch_persist_1"
