"""COM-209: ``Idempotency-Key`` de-duplication for create-order (and the forwarded charge).

Three layers are pinned here:

* **Service** — :class:`CreateOrderService` with in-memory doubles: a repeat with the same key
  replays the original order (no second create, no second charge, no re-published events); the same
  key with a *different* body is an :class:`IdempotencyConflictError`; a declined charge records no
  key (so the caller may retry); the client key is forwarded into the provider charge.
* **API** — ``POST /orders`` via dependency overrides: the ``Idempotency-Key`` header round-trips
  the same behaviour, and a conflict is a ``409`` problem document.
* **SQL store** — :class:`SqlIdempotencyStore` against the test database: ``save`` then ``find``
  round-trips per ``(user_id, key)``, and a duplicate ``save`` is tolerated (first write wins).
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
from app.domain.enums import FulfillmentType, PaymentMethodType
from app.domain.errors import IdempotencyConflictError, PaymentDeclinedError
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import DECLINE_TOKEN_PREFIX, FakePaymentProvider
from app.repositories.sql_idempotency_store import SqlIdempotencyStore
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
CARD_TOKEN = "tok_visa"
KEY = "idem-key-1"
KEY_A = "idem-key-a"
KEY_B = "idem-key-b"

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(USER_ID), email="a@b.com")


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


def _make_service(
    repo: InMemoryOrderRepository,
    payments: FakePaymentProvider,
    store: InMemoryIdempotencyStore,
    publisher: InMemoryEventPublisher,
) -> tuple[CreateOrderService, FakeMealPlanProvider]:
    provider = FakeMealPlanProvider(_snapshot())
    service = CreateOrderService(
        repo,
        provider,
        make_test_pricer(),
        publisher,
        payments,
        store,
    )
    return service, provider


# --------------------------------------------------------------------------- service layer


def test_same_key_same_body_replays_without_recreating():
    repo = InMemoryOrderRepository()
    publisher = InMemoryEventPublisher()
    service, provider = _make_service(
        repo, FakePaymentProvider(), InMemoryIdempotencyStore(), publisher
    )

    first = service.create(_command(), bearer_token=TOKEN, idempotency_key=KEY)
    second = service.create(_command(), bearer_token=TOKEN, idempotency_key=KEY)

    assert second.id == first.id
    assert len(repo.orders) == 1  # no second order created
    assert provider.calls == [(PLAN_ID, TOKEN)]  # plan fetched once — replay short-circuits
    assert len(publisher.published) == 1  # events not re-published on replay


def test_same_key_same_body_charges_card_once_and_forwards_key():
    payments = FakePaymentProvider()
    service, _ = _make_service(
        InMemoryOrderRepository(), payments, InMemoryIdempotencyStore(), InMemoryEventPublisher()
    )
    command = _command(payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token=CARD_TOKEN)

    first = service.create(command, bearer_token=TOKEN, idempotency_key=KEY)
    second = service.create(command, bearer_token=TOKEN, idempotency_key=KEY)

    assert second.id == first.id
    assert len(payments.charges) == 1  # charged only once
    assert payments.charges[0].idempotency_key == KEY  # key forwarded to the provider


def test_same_key_different_body_raises_conflict():
    service, _ = _make_service(
        InMemoryOrderRepository(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
        InMemoryEventPublisher(),
    )

    service.create(_command(), bearer_token=TOKEN, idempotency_key=KEY)

    conflicting = _command(delivery_time_slot="18:00-19:00")
    with pytest.raises(IdempotencyConflictError):
        service.create(conflicting, bearer_token=TOKEN, idempotency_key=KEY)


def test_distinct_keys_create_distinct_orders():
    repo = InMemoryOrderRepository()
    service, _ = _make_service(
        repo, FakePaymentProvider(), InMemoryIdempotencyStore(), InMemoryEventPublisher()
    )

    first = service.create(_command(), bearer_token=TOKEN, idempotency_key=KEY_A)
    second = service.create(_command(), bearer_token=TOKEN, idempotency_key=KEY_B)

    assert first.id != second.id
    assert len(repo.orders) == 2


def test_no_key_creates_distinct_orders():
    repo = InMemoryOrderRepository()
    service, _ = _make_service(
        repo, FakePaymentProvider(), InMemoryIdempotencyStore(), InMemoryEventPublisher()
    )

    first = service.create(_command(), bearer_token=TOKEN)
    second = service.create(_command(), bearer_token=TOKEN)

    assert first.id != second.id
    assert len(repo.orders) == 2


def test_declined_charge_records_no_key():
    store = InMemoryIdempotencyStore()
    service, _ = _make_service(
        InMemoryOrderRepository(), FakePaymentProvider(), store, InMemoryEventPublisher()
    )
    declined = _command(
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token=f"{DECLINE_TOKEN_PREFIX}_1",
    )

    with pytest.raises(PaymentDeclinedError):
        service.create(declined, bearer_token=TOKEN, idempotency_key=KEY)

    # A failed create memoises nothing, so the key is free for a genuine retry (COM-209).
    assert store.find(KEY, user_id=USER_ID) is None


# --------------------------------------------------------------------------- API: POST /orders

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


def _api_build() -> tuple[TestClient, InMemoryOrderRepository, FakePaymentProvider]:
    repo = InMemoryOrderRepository()
    payments = FakePaymentProvider()
    store = InMemoryIdempotencyStore()
    app.dependency_overrides[get_create_order_service] = lambda: CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        payments,
        store,
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo, payments


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_same_key_replays_same_order():
    client, repo, payments = _api_build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": CARD_TOKEN}}
    headers = {**_auth(), "Idempotency-Key": KEY}

    first = client.post("/orders", json=body, headers=headers)
    second = client.post("/orders", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(repo.orders) == 1  # only one order persisted
    assert len(payments.charges) == 1  # only one charge


def test_api_same_key_different_body_returns_409_problem_json():
    client, _, _ = _api_build()
    headers = {**_auth(), "Idempotency-Key": KEY}

    first = client.post("/orders", json=VALID_BODY, headers=headers)
    second = client.post(
        "/orders", json={**VALID_BODY, "deliveryTimeSlot": "18:00-19:00"}, headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")
    assert second.json()["status"] == 409


def test_api_no_key_creates_two_orders():
    client, repo, _ = _api_build()

    first = client.post("/orders", json=VALID_BODY, headers=_auth())
    second = client.post("/orders", json=VALID_BODY, headers=_auth())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert len(repo.orders) == 2


def test_api_forwards_idempotency_key_to_provider():
    client, _, payments = _api_build()
    body = {**VALID_BODY, "paymentMethod": {"type": "credit_card", "token": CARD_TOKEN}}
    headers = {**_auth(), "Idempotency-Key": KEY}

    response = client.post("/orders", json=body, headers=headers)

    assert response.status_code == 201
    assert payments.charges[0].idempotency_key == KEY


# --------------------------------------------------------------------------- SQL store round-trip


def test_sql_store_save_then_find(db_session):
    store = SqlIdempotencyStore(db_session)
    order_id = uuid.uuid4()

    store.save(KEY, user_id=USER_ID, order_id=order_id, request_fingerprint="fp-1")

    found = store.find(KEY, user_id=USER_ID)
    assert found is not None
    assert found.key == KEY
    assert found.order_id == order_id
    assert found.request_fingerprint == "fp-1"
    # Scoped per user and per key: another user or another key sees nothing.
    assert store.find(KEY, user_id=uuid.uuid4()) is None
    assert store.find("other-key", user_id=USER_ID) is None


def test_sql_store_duplicate_save_is_tolerated(db_session):
    store = SqlIdempotencyStore(db_session)
    first_order = uuid.uuid4()

    store.save(KEY, user_id=USER_ID, order_id=first_order, request_fingerprint="fp-1")
    # A concurrent duplicate on the unique (user_id, key) is swallowed — the first write wins.
    store.save(KEY, user_id=USER_ID, order_id=uuid.uuid4(), request_fingerprint="fp-2")

    found = store.find(KEY, user_id=USER_ID)
    assert found is not None
    assert found.order_id == first_order
    assert found.request_fingerprint == "fp-1"
