"""COM-109: order domain events, the versioned envelope, and service publishing.

Covers the whole recording-to-bus path with no DB or network:

* the ``Order`` aggregate records an :class:`OrderCreated` only when told to (never on rehydrate)
  and drains it via :meth:`pull_events`;
* :func:`to_envelope` produces the versioned, JSON-native wire shape and maps each event to the
  right ``type`` (``order.created`` / ``order.confirmed`` / ``order.status_changed``);
* the create/cancel use cases publish the drained events through the injected
  :class:`EventPublisher`, and a failed create publishes nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.application.cancel_order import CancelOrderService
from app.application.commands import CancelOrderCommand, CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import MealPlanNotFoundError
from app.domain.events import OrderCreated, OrderStatusChanged
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.events.envelope import (
    EVENT_TYPE_CONFIRMED,
    EVENT_TYPE_CREATED,
    EVENT_TYPE_STATUS_CHANGED,
    SCHEMA_VERSION,
    event_type,
    to_envelope,
)
from app.events.memory import InMemoryEventPublisher
from app.payments.fake import FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    make_test_pricer,
)

USER_ID = uuid.uuid4()
PLAN_ID = str(uuid.uuid4())
TOKEN = "caller-token"


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _order(*, status: OrderStatus = OrderStatus.PENDING, user_id: uuid.UUID = USER_ID) -> Order:
    return Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
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
    )
    base.update(overrides)
    return CreateOrderCommand(**base)


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
        ],
    )


# --------------------------------------------------------------------------- domain: recording


def test_record_created_appends_order_created_event():
    order = _order()

    order.record_created()

    events = order.pull_events()
    assert events == [
        OrderCreated(order_id=order.id, user_id=order.user_id, occurred_at=order.created_at)
    ]


def test_record_created_defaults_occurred_at_to_created_at():
    order = _order()

    order.record_created()

    assert order.pull_events()[0].occurred_at == order.created_at


def test_fresh_order_records_nothing():
    # Guards against recording in __init__: a rehydrated/stored order must emit no event.
    assert _order().pull_events() == []


def test_pull_events_drains_so_a_second_pull_is_empty():
    order = _order()
    order.record_created()

    assert len(order.pull_events()) == 1
    assert order.pull_events() == []


def test_cancel_records_status_changed_event():
    order = _order(status=OrderStatus.PENDING)

    order.cancel()

    [event] = order.pull_events()
    assert isinstance(event, OrderStatusChanged)
    assert event.from_status is OrderStatus.PENDING
    assert event.to_status is OrderStatus.CANCELLED


# --------------------------------------------------------------------------- envelope


def test_created_envelope_is_versioned_and_camelcase():
    order_id, user_id = uuid.uuid4(), uuid.uuid4()
    event = OrderCreated(order_id=order_id, user_id=user_id, occurred_at=_order().created_at)
    event_id = uuid.uuid4()

    envelope = to_envelope(event, event_id=event_id)

    assert envelope == {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(event_id),
        "type": EVENT_TYPE_CREATED,
        "occurredAt": event.occurred_at.isoformat(),
        "data": {"orderId": str(order_id), "userId": str(user_id)},
    }


def test_schema_version_is_one():
    assert SCHEMA_VERSION == 1


def _status_change(to_status: OrderStatus, *, frm: OrderStatus = OrderStatus.PENDING):
    return OrderStatusChanged(
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        from_status=frm,
        to_status=to_status,
        occurred_at=_order().created_at,
    )


def test_confirmed_transition_maps_to_order_confirmed():
    event = _status_change(OrderStatus.CONFIRMED)

    envelope = to_envelope(event)

    assert envelope["type"] == EVENT_TYPE_CONFIRMED
    assert envelope["data"] == {
        "orderId": str(event.order_id),
        "userId": str(event.user_id),
        "fromStatus": "pending",
        "toStatus": "confirmed",
    }


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (OrderStatus.PENDING, OrderStatus.CANCELLED),
        (OrderStatus.PREPARING, OrderStatus.IN_TRANSIT),
        (OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED),
    ],
)
def test_other_transitions_map_to_status_changed(frm: OrderStatus, to: OrderStatus):
    assert event_type(_status_change(to, frm=frm)) == EVENT_TYPE_STATUS_CHANGED


def test_envelope_is_json_serializable():
    envelope = to_envelope(_status_change(OrderStatus.CANCELLED))

    assert json.loads(json.dumps(envelope)) == envelope


def test_event_id_is_generated_uniquely_per_publish():
    event = OrderCreated(
        order_id=uuid.uuid4(), user_id=uuid.uuid4(), occurred_at=_order().created_at
    )

    assert to_envelope(event)["id"] != to_envelope(event)["id"]


# --------------------------------------------------------------------------- in-memory publisher


def test_in_memory_publisher_records_in_order():
    publisher = InMemoryEventPublisher()
    first = OrderCreated(
        order_id=uuid.uuid4(), user_id=uuid.uuid4(), occurred_at=_order().created_at
    )
    second = _status_change(OrderStatus.CANCELLED)

    publisher.publish(first)
    publisher.publish(second)

    assert publisher.published == [first, second]


# --------------------------------------------------------------------------- service integration


def test_create_service_publishes_order_created():
    repo = InMemoryOrderRepository()
    publisher = InMemoryEventPublisher()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        publisher,
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    )

    order = service.create(_command(), bearer_token=TOKEN)

    assert len(publisher.published) == 1
    [event] = publisher.published
    assert isinstance(event, OrderCreated)
    assert event.order_id == order.id
    assert event.user_id == order.user_id
    assert event_type(event) == EVENT_TYPE_CREATED


def test_failed_create_publishes_nothing():
    repo = InMemoryOrderRepository()
    publisher = InMemoryEventPublisher()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(None),
        make_test_pricer(),
        publisher,
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    )

    with pytest.raises(MealPlanNotFoundError):
        service.create(_command(), bearer_token=TOKEN)

    assert publisher.published == []


def test_cancel_service_publishes_status_changed():
    order = _order(status=OrderStatus.PENDING)
    repo = InMemoryOrderRepository()
    repo.add(order)
    publisher = InMemoryEventPublisher()
    service = CancelOrderService(repo, publisher)

    service.cancel(CancelOrderCommand(user_id=USER_ID, order_id=order.id))

    assert len(publisher.published) == 1
    [event] = publisher.published
    assert isinstance(event, OrderStatusChanged)
    assert event.to_status is OrderStatus.CANCELLED
    assert event_type(event) == EVENT_TYPE_STATUS_CHANGED
