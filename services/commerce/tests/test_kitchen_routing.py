"""COM-303: dark-kitchen routing — domain ticket, order status methods, router, and confirm paths.

Covers the *outbound* half of dark-kitchen fulfilment: a confirmed dark-kitchen order is turned
into a :class:`KitchenTicket` and handed to the kitchen queue, from *both* confirm paths -- the
inline card charge at checkout (COM-202) and the asynchronous payment webhook (COM-206). Routing is
guarded (only confirmed dark-kitchen orders) and best-effort (a queue outage never fails a committed
order). Also pins the idempotent ``Order.report_preparing`` / ``report_dispatched`` status methods
the inbound kitchen webhook (COM-303) drives.

Everything runs offline via in-memory doubles.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.adapters.in_memory_kitchen_queue import InMemoryKitchenQueue
from app.application.create_order import CreateOrderService
from app.application.route_to_kitchen import KitchenRouter
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import IllegalOrderTransitionError
from app.domain.kitchen import KitchenTicket, KitchenTicketItem
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.payments.fake import DECLINE_TOKEN_PREFIX, FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
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


def _dark_kitchen_order(*, confirmed: bool = True) -> Order:
    """A dark-kitchen order with two priced line items, optionally already confirmed."""
    order = Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        provider_id="kitchen-1",
        notes="Ring the bell",
    )
    pricer = make_test_pricer()
    order.add_item(
        pricer.price_item(
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl")
        )
    )
    order.add_item(
        pricer.price_item(PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None))
    )
    if confirmed:
        order.confirm()
        order.pull_events()
    return order


class _FailingKitchenQueue:
    """A queue whose ``route`` always raises, to prove routing is best-effort."""

    def route(self, ticket: KitchenTicket) -> None:
        raise RuntimeError("kitchen queue is down")


# --------------------------------------------------------------------------------------------------
# Domain: KitchenTicket.for_order
# --------------------------------------------------------------------------------------------------


def test_ticket_is_built_from_a_confirmed_dark_kitchen_order():
    order = _dark_kitchen_order()

    ticket = KitchenTicket.for_order(order)

    assert ticket.order_id == order.id
    assert ticket.user_id == USER_ID
    assert ticket.delivery_date == date(2026, 7, 10)
    assert ticket.delivery_time_slot == "12:00-13:00"
    assert ticket.provider_id == "kitchen-1"
    assert ticket.notes == "Ring the bell"


def test_ticket_maps_each_order_item_to_a_ticket_item():
    order = _dark_kitchen_order()

    ticket = KitchenTicket.for_order(order)

    assert len(ticket.items) == len(order.items)
    assert all(isinstance(item, KitchenTicketItem) for item in ticket.items)
    for ticket_item, order_item in zip(ticket.items, order.items, strict=True):
        assert ticket_item.name == order_item.name
        assert ticket_item.quantity == order_item.quantity
        assert ticket_item.unit == order_item.unit


def test_ticket_items_are_an_immutable_tuple():
    ticket = KitchenTicket.for_order(_dark_kitchen_order())

    assert isinstance(ticket.items, tuple)


# --------------------------------------------------------------------------------------------------
# Domain: Order.report_preparing / report_dispatched (idempotent + guarded)
# --------------------------------------------------------------------------------------------------


def test_report_preparing_advances_confirmed_to_preparing():
    order = _dark_kitchen_order()

    order.report_preparing()

    assert order.status is OrderStatus.PREPARING
    assert [e.to_status for e in order.pull_events()] == [OrderStatus.PREPARING]


def test_report_preparing_is_idempotent_on_redelivery():
    order = _dark_kitchen_order()
    order.report_preparing()
    order.pull_events()

    order.report_preparing()

    assert order.status is OrderStatus.PREPARING
    assert order.pull_events() == []  # the no-op recorded nothing


def test_report_preparing_is_a_no_op_once_further_along():
    order = _dark_kitchen_order()
    order.report_preparing()
    order.report_dispatched()  # now in_transit
    order.pull_events()

    order.report_preparing()

    assert order.status is OrderStatus.IN_TRANSIT
    assert order.pull_events() == []


def test_report_preparing_on_a_pending_order_conflicts():
    order = _dark_kitchen_order(confirmed=False)

    with pytest.raises(IllegalOrderTransitionError):
        order.report_preparing()
    assert order.status is OrderStatus.PENDING


def test_report_dispatched_advances_preparing_to_in_transit():
    order = _dark_kitchen_order()
    order.report_preparing()
    order.pull_events()

    order.report_dispatched()

    assert order.status is OrderStatus.IN_TRANSIT
    assert [e.to_status for e in order.pull_events()] == [OrderStatus.IN_TRANSIT]


def test_report_dispatched_is_idempotent_on_redelivery():
    order = _dark_kitchen_order()
    order.report_preparing()
    order.report_dispatched()
    order.pull_events()

    order.report_dispatched()

    assert order.status is OrderStatus.IN_TRANSIT
    assert order.pull_events() == []


def test_report_dispatched_before_preparing_conflicts():
    order = _dark_kitchen_order()  # confirmed, not yet preparing

    with pytest.raises(IllegalOrderTransitionError):
        order.report_dispatched()
    assert order.status is OrderStatus.CONFIRMED


# --------------------------------------------------------------------------------------------------
# Application: KitchenRouter.route (guards + best-effort)
# --------------------------------------------------------------------------------------------------


def test_router_routes_a_confirmed_dark_kitchen_order():
    queue = InMemoryKitchenQueue()
    order = _dark_kitchen_order()

    KitchenRouter(queue).route(order)

    assert len(queue.tickets) == 1
    assert queue.tickets[0].order_id == order.id


def test_router_skips_a_pending_dark_kitchen_order():
    queue = InMemoryKitchenQueue()

    KitchenRouter(queue).route(_dark_kitchen_order(confirmed=False))

    assert queue.tickets == []


@pytest.mark.parametrize(
    "fulfillment_type", [FulfillmentType.GROCERY_DELIVERY, FulfillmentType.PICKUP]
)
def test_router_skips_a_non_dark_kitchen_order(fulfillment_type: FulfillmentType):
    queue = InMemoryKitchenQueue()
    order = _dark_kitchen_order()
    order.fulfillment_type = fulfillment_type  # confirmed, but not a dark-kitchen order

    KitchenRouter(queue).route(order)

    assert queue.tickets == []


def test_router_swallows_a_queue_failure():
    order = _dark_kitchen_order()

    # Best-effort: the order is already committed, so a queue outage must not propagate.
    KitchenRouter(_FailingKitchenQueue()).route(order)


# --------------------------------------------------------------------------------------------------
# Integration: CreateOrderService routes a card-confirmed dark-kitchen order (COM-202 path)
# --------------------------------------------------------------------------------------------------


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Oatmeal Bowl"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name=None),
        ],
    )


def _command(**overrides):
    from app.application.commands import CreateOrderCommand

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


def _create_service(
    queue: InMemoryKitchenQueue,
) -> tuple[CreateOrderService, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
        KitchenRouter(queue),
    )
    return service, repo


def test_create_routes_a_card_confirmed_dark_kitchen_order():
    queue = InMemoryKitchenQueue()
    service, _ = _create_service(queue)

    order = service.create(
        _command(payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token=CARD_TOKEN),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.CONFIRMED
    assert [t.order_id for t in queue.tickets] == [order.id]


def test_create_does_not_route_an_async_pending_dark_kitchen_order():
    queue = InMemoryKitchenQueue()
    service, _ = _create_service(queue)

    # An OXXO order stays pending until a webhook settles it, so nothing is routed at create time.
    order = service.create(_command(payment_method_type=PaymentMethodType.OXXO), bearer_token=TOKEN)

    assert order.status is OrderStatus.PENDING
    assert queue.tickets == []


def test_create_does_not_route_a_confirmed_grocery_order():
    queue = InMemoryKitchenQueue()
    service, _ = _create_service(queue)

    order = service.create(
        _command(
            fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
            provider_id="grocer-1",
            payment_method_type=PaymentMethodType.CREDIT_CARD,
            payment_token=CARD_TOKEN,
        ),
        bearer_token=TOKEN,
    )

    assert order.status is OrderStatus.CONFIRMED
    assert queue.tickets == []


def test_create_declined_card_routes_nothing():
    queue = InMemoryKitchenQueue()
    service, _ = _create_service(queue)

    from app.domain.errors import PaymentDeclinedError

    with pytest.raises(PaymentDeclinedError):
        service.create(
            _command(
                payment_method_type=PaymentMethodType.CREDIT_CARD,
                payment_token=f"{DECLINE_TOKEN_PREFIX}_1",
            ),
            bearer_token=TOKEN,
        )
    assert queue.tickets == []


# --------------------------------------------------------------------------------------------------
# Integration: the payment webhook routes a now-confirmed dark-kitchen order (COM-206 path)
# --------------------------------------------------------------------------------------------------

WEBHOOK_SECRET = "fake-webhook-secret-not-a-real-key"  # gitleaks:allow


def _sign(payload: bytes) -> str:
    import hashlib
    import hmac

    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _confirm_event(reference: str) -> bytes:
    import json

    return json.dumps({"type": "payment.confirmed", "data": {"reference": reference}}).encode(
        "utf-8"
    )


def _async_pending_dark_kitchen_order() -> Order:
    """A ``pending`` dark-kitchen order awaiting settlement (as an issued SPEI transfer leaves)."""
    from datetime import UTC, datetime

    order = _dark_kitchen_order(confirmed=False)
    order.attach_transfer(
        provider="fake",
        clabe="012345678901234567",
        reference="spei_abc123",
        expires_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    return order


def test_payment_webhook_routes_a_confirmed_dark_kitchen_order():
    from app.application.process_payment_webhook import ProcessPaymentWebhookService

    queue = InMemoryKitchenQueue()
    order = _async_pending_dark_kitchen_order()
    repo = InMemoryOrderRepository()
    repo.add(order)
    service = ProcessPaymentWebhookService(
        repo,
        FakePaymentProvider(webhook_secret=WEBHOOK_SECRET),
        InMemoryEventPublisher(),
        KitchenRouter(queue),
    )
    payload = _confirm_event(str(order.id))

    settled = service.process(payload=payload, signature=_sign(payload))

    assert settled.status is OrderStatus.CONFIRMED
    assert [t.order_id for t in queue.tickets] == [order.id]


def test_payment_webhook_does_not_route_a_failed_order():
    import json

    from app.application.process_payment_webhook import ProcessPaymentWebhookService

    queue = InMemoryKitchenQueue()
    order = _async_pending_dark_kitchen_order()
    repo = InMemoryOrderRepository()
    repo.add(order)
    service = ProcessPaymentWebhookService(
        repo,
        FakePaymentProvider(webhook_secret=WEBHOOK_SECRET),
        InMemoryEventPublisher(),
        KitchenRouter(queue),
    )
    payload = json.dumps({"type": "payment.failed", "data": {"reference": str(order.id)}}).encode(
        "utf-8"
    )

    settled = service.process(payload=payload, signature=_sign(payload))

    assert settled.status is OrderStatus.CANCELLED
    assert queue.tickets == []
