"""COM-304: dark-kitchen delivery-slot reservation + conflict handling.

The capacity **write path** that backs availability (COM-302). Covers four layers:

* the SQL store (:class:`SqlSlotReservationStore`) -- its atomic count-guarded ``reserve`` (a full
  window raises :class:`SlotUnavailableError`), ``release`` (idempotent), and ``booked_counts``
  scoped by ``(zone, date, slot)``;
* the :class:`ReserveDeliverySlotService` policy -- dark-kitchen-gated reserve using the service
  area's capacity, and an idempotent release;
* the create/cancel/webhook flows wired to a *real* SQL store sharing one unit of work, proving the
  reservation commits atomically with the order (a declined payment rolls it back, a cancellation or
  a failed-payment webhook frees it); and
* the HTTP edges -- an over-capacity ``POST /orders`` is a ``409`` problem document, and
  ``GET /fulfillment/dark-kitchen/availability`` now reflects a genuine booking.

The store/flow tests run against the conftest test database (Postgres in CI, throwaway SQLite
locally); the reservation row commits only alongside the order, so ``reserve``/``release`` merely
``flush``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import (
    get_dark_kitchen_service_area,
    get_meal_plan_provider,
    get_token_verifier,
)
from app.application.cancel_order import CancelOrderService
from app.application.commands import CancelOrderCommand, CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.application.reserve_slot import ReserveDeliverySlotService
from app.core.principal import Principal
from app.db.models import OrderModel
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import PaymentDeclinedError, SlotUnavailableError
from app.domain.fulfillment import DarkKitchenServiceArea
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import DECLINE_TOKEN_PREFIX, FakePaymentProvider
from app.repositories.sql_order_repository import SqlOrderRepository
from app.repositories.sql_slot_reservation_store import SqlSlotReservationStore
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    StubVerifier,
    make_test_pricer,
)

GOOD_TOKEN = "good-token"
TOKEN = "caller-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER_ID = uuid.uuid4()
PLAN_ID = str(uuid.uuid4())

ZIP = "06600"
DAY = date(2026, 7, 10)
SLOT = "12:00-13:00"
SLOTS = ("09:00-11:00", "11:00-13:00", "13:00-15:00")
WEBHOOK_SECRET = "fake-webhook-secret-not-a-real-key"  # gitleaks:allow


def _address(zip_code: str = ZIP) -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code=zip_code, country="MX"
    )


def _area(capacity: int) -> DarkKitchenServiceArea:
    return DarkKitchenServiceArea(
        served_zip_prefixes=("06",), time_slots=SLOTS, slot_capacity=capacity
    )


def _order(*, fulfillment: FulfillmentType = FulfillmentType.DARK_KITCHEN) -> Order:
    return Order(
        user_id=USER_ID,
        fulfillment_type=fulfillment,
        delivery_address=_address(),
        delivery_date=DAY,
        delivery_time_slot=SLOT,
    )


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal")],
    )


def _command(**overrides) -> CreateOrderCommand:
    base = dict(
        user_id=USER_ID,
        meal_plan_id=PLAN_ID,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=DAY,
        delivery_time_slot=SLOT,
        provider_id=None,
        notes=None,
        payment_method_type=None,
        payment_token=None,
    )
    base.update(overrides)
    return CreateOrderCommand(**base)


def _order_count(session) -> int:
    return int(session.execute(select(func.count()).select_from(OrderModel)).scalar_one())


# ============================================================================ SQL store adapter


def test_reserve_then_booked_counts_reflects_the_booking(db_session):
    store = SqlSlotReservationStore(db_session)

    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=5)

    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}


def test_reserve_counts_each_slot_independently(db_session):
    store = SqlSlotReservationStore(db_session)

    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOTS[0], order_id=uuid.uuid4(), capacity=5)
    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOTS[1], order_id=uuid.uuid4(), capacity=5)

    assert store.booked_counts(ZIP, DAY) == {SLOTS[0]: 1, SLOTS[1]: 1}


def test_reserve_enforces_capacity_atomically(db_session):
    store = SqlSlotReservationStore(db_session)

    def book() -> None:
        store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=2)

    book()
    book()  # capacity of 2 reached

    with pytest.raises(SlotUnavailableError):
        book()
    assert store.booked_counts(ZIP, DAY) == {SLOT: 2}


def test_slot_unavailable_error_carries_the_window(db_session):
    store = SqlSlotReservationStore(db_session)
    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=1)

    with pytest.raises(SlotUnavailableError) as excinfo:
        store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=1)

    assert excinfo.value.zip_code == ZIP
    assert excinfo.value.delivery_date == DAY
    assert excinfo.value.slot == SLOT


def test_release_frees_capacity_for_rebooking(db_session):
    store = SqlSlotReservationStore(db_session)
    held = uuid.uuid4()
    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=held, capacity=1)
    with pytest.raises(SlotUnavailableError):
        store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=1)

    store.release(order_id=held)

    # The freed unit can be booked again.
    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=1)
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}


def test_release_is_idempotent(db_session):
    store = SqlSlotReservationStore(db_session)

    store.release(order_id=uuid.uuid4())  # nothing booked -> no error, no rows

    assert store.booked_counts(ZIP, DAY) == {}


def test_booked_counts_are_scoped_by_zone_and_date(db_session):
    store = SqlSlotReservationStore(db_session)
    store.reserve(zip_code=ZIP, delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=9)
    store.reserve(zip_code="99999", delivery_date=DAY, slot=SLOT, order_id=uuid.uuid4(), capacity=9)
    store.reserve(
        zip_code=ZIP, delivery_date=date(2026, 8, 1), slot=SLOT, order_id=uuid.uuid4(), capacity=9
    )

    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}


# =================================================================== ReserveDeliverySlotService


class _RecordingStore:
    """A :class:`SlotReservationStore` double recording reserve/release, optionally raising."""

    def __init__(self) -> None:
        self.reserved: list[tuple[str, date, str, uuid.UUID, int]] = []
        self.released: list[uuid.UUID] = []
        self.error: Exception | None = None

    def booked_counts(self, zip_code: str, delivery_date: date):
        return {}

    def reserve(self, *, zip_code, delivery_date, slot, order_id, capacity) -> None:
        if self.error is not None:
            raise self.error
        self.reserved.append((zip_code, delivery_date, slot, order_id, capacity))

    def release(self, *, order_id) -> None:
        self.released.append(order_id)


def test_service_reserves_for_dark_kitchen_with_area_capacity():
    store = _RecordingStore()
    service = ReserveDeliverySlotService(_area(7), store)
    order = _order()

    service.reserve_for(order)

    assert store.reserved == [(ZIP, DAY, SLOT, order.id, 7)]


@pytest.mark.parametrize("fulfillment", [FulfillmentType.PICKUP, FulfillmentType.GROCERY_DELIVERY])
def test_service_ignores_non_dark_kitchen_orders(fulfillment: FulfillmentType):
    store = _RecordingStore()
    service = ReserveDeliverySlotService(_area(5), store)

    service.reserve_for(_order(fulfillment=fulfillment))

    assert store.reserved == []


def test_service_release_delegates_to_store():
    store = _RecordingStore()
    service = ReserveDeliverySlotService(_area(5), store)
    order_id = uuid.uuid4()

    service.release_for(order_id)

    assert store.released == [order_id]


def test_service_reserve_propagates_slot_unavailable():
    store = _RecordingStore()
    store.error = SlotUnavailableError(zip_code=ZIP, delivery_date=DAY, slot=SLOT)
    service = ReserveDeliverySlotService(_area(1), store)

    with pytest.raises(SlotUnavailableError):
        service.reserve_for(_order())


# ============================================================ create / cancel / webhook (real SQL)


def _sql_stack(db_session, *, area, payments=None):
    """Wire the real SQL order repo + slot store into create/cancel, sharing one unit of work."""
    repo = SqlOrderRepository(db_session)
    store = SqlSlotReservationStore(db_session)
    reserve = ReserveDeliverySlotService(area, store)
    publisher = InMemoryEventPublisher()
    pay = payments if payments is not None else FakePaymentProvider()
    create = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        publisher,
        pay,
        InMemoryIdempotencyStore(),
        slot_reservations=reserve,
    )
    cancel = CancelOrderService(repo, pay, publisher, slot_reservations=reserve)
    return create, cancel, repo, store


def test_create_dark_kitchen_order_reserves_a_slot(db_session):
    create, _, repo, store = _sql_stack(db_session, area=_area(5))

    order = create.create(_command(), bearer_token=TOKEN)

    # orders.add() committed the order and, in the same unit of work, the reservation.
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}
    assert repo.get(order.id, user_id=USER_ID) is not None


def test_create_non_dark_kitchen_order_reserves_nothing(db_session):
    create, _, _, store = _sql_stack(db_session, area=_area(5))

    create.create(_command(fulfillment_type=FulfillmentType.PICKUP), bearer_token=TOKEN)

    assert store.booked_counts(ZIP, DAY) == {}


def test_over_capacity_second_create_is_rejected_and_not_persisted(db_session):
    create, _, _, store = _sql_stack(db_session, area=_area(1))
    create.create(_command(), bearer_token=TOKEN)  # takes the only unit

    with pytest.raises(SlotUnavailableError):
        create.create(_command(), bearer_token=TOKEN)

    # The full slot placed no second order; the first booking is intact.
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}
    assert _order_count(db_session) == 1


def test_payment_decline_rolls_back_the_reservation(db_session):
    create, _, _, store = _sql_stack(db_session, area=_area(1))

    with pytest.raises(PaymentDeclinedError):
        create.create(
            _command(
                payment_method_type=PaymentMethodType.CREDIT_CARD,
                payment_token=f"{DECLINE_TOKEN_PREFIX}_1",
            ),
            bearer_token=TOKEN,
        )

    # The reservation was flushed before the charge; the decline aborts before commit. Mirror the
    # request lifecycle (get_db closes the session -> ROLLBACK) and assert nothing was persisted.
    db_session.rollback()
    assert store.booked_counts(ZIP, DAY) == {}
    assert _order_count(db_session) == 0


def test_cancel_releases_the_slot_for_rebooking(db_session):
    create, cancel, _, store = _sql_stack(db_session, area=_area(1))
    order = create.create(_command(), bearer_token=TOKEN)
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}

    cancelled = cancel.cancel(CancelOrderCommand(user_id=USER_ID, order_id=order.id))

    assert cancelled.status is OrderStatus.CANCELLED
    assert store.booked_counts(ZIP, DAY) == {}
    # The freed capacity is bookable again by a fresh order.
    again = create.create(_command(), bearer_token=TOKEN)
    assert again.id != order.id
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}


def _sign(payload: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _failed_event(reference: str) -> bytes:
    return json.dumps({"type": "payment.failed", "data": {"reference": reference}}).encode("utf-8")


def test_failed_payment_webhook_releases_the_slot(db_session):
    payments = FakePaymentProvider(webhook_secret=WEBHOOK_SECRET)
    create, _, repo, store = _sql_stack(db_session, area=_area(1), payments=payments)
    order = create.create(_command(payment_method_type=PaymentMethodType.OXXO), bearer_token=TOKEN)
    assert order.status is OrderStatus.PENDING
    assert store.booked_counts(ZIP, DAY) == {SLOT: 1}

    webhook = ProcessPaymentWebhookService(
        repo,
        payments,
        InMemoryEventPublisher(),
        slot_reservations=ReserveDeliverySlotService(_area(1), store),
    )
    payload = _failed_event(str(order.id))
    settled = webhook.process(payload=payload, signature=_sign(payload))

    assert settled.status is OrderStatus.CANCELLED
    assert store.booked_counts(ZIP, DAY) == {}


# ================================================================================== HTTP edges

_AVAIL_URL = "/fulfillment/dark-kitchen/availability"
_API_PLAN_ID = str(uuid.uuid4())
_API_BODY = {
    "mealPlanId": _API_PLAN_ID,
    "fulfillmentType": "dark_kitchen",
    "deliveryAddress": {
        "street": "Av. Reforma 100",
        "city": "CDMX",
        "state": "CDMX",
        "zipCode": ZIP,
        "country": "MX",
    },
    "deliveryDate": DAY.isoformat(),
    "deliveryTimeSlot": SLOT,
}


def _api_snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=_API_PLAN_ID,
        meals=[PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal")],
    )


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    for dep in (get_dark_kitchen_service_area, get_meal_plan_provider, get_token_verifier):
        app.dependency_overrides.pop(dep, None)


def test_create_over_capacity_returns_409_problem_json():
    # Real create wiring (SQL repo + SQL reservation store) with a capacity-1 area.
    app.dependency_overrides[get_dark_kitchen_service_area] = lambda: _area(1)
    app.dependency_overrides[get_meal_plan_provider] = lambda: FakeMealPlanProvider(_api_snapshot())
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    client = TestClient(app)

    first = client.post("/orders", json=_API_BODY, headers=_auth())
    assert first.status_code == 201

    second = client.post("/orders", json=_API_BODY, headers=_auth())
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")
    assert second.json()["status"] == 409


def test_availability_endpoint_reflects_a_real_reservation(db_session):
    booked_day = date(2999, 1, 1)
    # Book the first window to its (overridden) capacity of 1, committed so the request sees it.
    store = SqlSlotReservationStore(db_session)
    store.reserve(
        zip_code=ZIP, delivery_date=booked_day, slot=SLOTS[0], order_id=uuid.uuid4(), capacity=1
    )
    db_session.commit()

    app.dependency_overrides[get_dark_kitchen_service_area] = lambda: _area(1)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    client = TestClient(app)

    response = client.get(
        _AVAIL_URL, params={"zipCode": ZIP, "deliveryDate": booked_day.isoformat()}, headers=_auth()
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert SLOTS[0] not in data["timeSlots"]  # booked out -> omitted
    assert SLOTS[1] in data["timeSlots"]  # still open
