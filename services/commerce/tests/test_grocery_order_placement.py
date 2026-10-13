"""COM-408: a confirmed grocery order is placed with its provider through the ACL (AC1).

Covers the *outbound* half of grocery fulfilment: once an order is confirmed, its line items are
resolved to provider SKUs and an order is placed with the provider, from *both* confirm paths -- the
inline card charge at checkout (COM-202) and the asynchronous payment webhook (COM-206). Placement
is guarded (only confirmed, unplaced grocery orders), idempotent (a redelivered confirmation never
buys the groceries twice) and best-effort (a provider outage never fails a committed order).

Everything runs offline via in-memory doubles.
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
from app.application.place_grocery_order import GroceryOrderPlacer
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import GroceryProviderUnavailableError, OrderValidationError
from app.domain.grocery_catalog import GroceryOrderStatus
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.domain.payment import PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.grocery.fake import FakeGroceryProviderAdapter
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
CARD_TOKEN = "tok_visa"
PROVIDER_ID = "freshbasket"
WEBHOOK_SECRET = "fake-grocery-webhook-secret-not-real"  # gitleaks:allow


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _grocery_order(*, confirmed: bool = True, provider_id: str | None = PROVIDER_ID) -> Order:
    """A grocery order for milk, eggs and (out-of-stock) bread, optionally already confirmed."""
    order = Order(
        user_id=USER_ID,
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=_address(),
        delivery_date=date(2026, 9, 10),
        delivery_time_slot="09:00-11:00",
        provider_id=provider_id,
    )
    pricer = make_test_pricer()
    for name, servings in (("Milk", "1"), ("Eggs", "2"), ("Bread", "1")):
        order.add_item(
            pricer.price_item(
                PlannedMeal(meal_type="breakfast", servings=Decimal(servings), recipe_name=name)
            )
        )
    if confirmed:
        order.confirm()
        order.pull_events()
    return order


def _placer(
    adapter: FakeGroceryProviderAdapter | None = None,
) -> tuple[GroceryOrderPlacer, InMemoryOrderRepository, FakeGroceryProviderAdapter]:
    adapter = adapter or FakeGroceryProviderAdapter(PROVIDER_ID)
    repo = InMemoryOrderRepository()
    placer = GroceryOrderPlacer(repo, {PROVIDER_ID: adapter}, InMemoryEventPublisher())
    return placer, repo, adapter


class _FailingGroceryAdapter:
    """An adapter whose every call fails, to prove placement is best-effort."""

    provider_id = PROVIDER_ID

    def search(self, query):  # noqa: ANN001, ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)

    def place_order(self, request):  # noqa: ANN001, ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)

    def get_order_status(self, external_order_id: str):  # noqa: ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)


def _snapshot() -> MealPlanSnapshot:
    return MealPlanSnapshot(
        plan_id=PLAN_ID,
        meals=[
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Milk"),
            PlannedMeal(meal_type="lunch", servings=Decimal("2"), recipe_name="Eggs"),
        ],
    )


# --------------------------------------------------------------------------------------------------
# Domain: Order.record_grocery_placement
# --------------------------------------------------------------------------------------------------


def test_recording_a_placement_stores_the_provider_reference_and_status():
    order = _grocery_order()

    order.record_grocery_placement(external_order_id="fb_ord_1", status=GroceryOrderStatus.PENDING)

    assert order.grocery_external_order_id == "fb_ord_1"
    assert order.grocery_status is GroceryOrderStatus.PENDING
    assert order.is_placed_with_provider is True


def test_a_pending_placement_does_not_move_the_order_lifecycle():
    order = _grocery_order()
    confirmed_history = len(order.status_history)

    order.record_grocery_placement(external_order_id="fb_ord_1", status=GroceryOrderStatus.PENDING)

    assert order.status is OrderStatus.CONFIRMED
    assert len(order.status_history) == confirmed_history
    assert order.pull_events() == []


def test_a_placement_that_is_already_preparing_moves_the_order():
    order = _grocery_order()

    order.record_grocery_placement(
        external_order_id="fb_ord_1", status=GroceryOrderStatus.PREPARING
    )

    assert order.status is OrderStatus.PREPARING


def test_a_placement_requires_the_providers_order_id():
    order = _grocery_order()

    with pytest.raises(OrderValidationError):
        order.record_grocery_placement(external_order_id="", status=GroceryOrderStatus.PENDING)

    assert order.is_placed_with_provider is False


# --------------------------------------------------------------------------------------------------
# Placer guards
# --------------------------------------------------------------------------------------------------


def test_a_dark_kitchen_order_is_not_placed_with_a_grocery_provider():
    placer, _, adapter = _placer()
    order = _grocery_order()
    order.fulfillment_type = FulfillmentType.DARK_KITCHEN

    assert placer.place(order) is None
    assert adapter.orders == []


def test_an_unconfirmed_order_is_not_placed():
    placer, _, adapter = _placer()

    assert placer.place(_grocery_order(confirmed=False)) is None
    assert adapter.orders == []


def test_an_order_without_a_provider_is_not_placed():
    placer, _, adapter = _placer()
    order = _grocery_order(provider_id=None)

    assert placer.place(order) is None
    assert adapter.orders == []


def test_an_order_whose_provider_has_no_adapter_is_not_placed():
    placer, _, adapter = _placer()
    order = _grocery_order(provider_id="chedraui")

    assert placer.place(order) is None
    assert adapter.orders == []
    assert order.is_placed_with_provider is False


def test_an_already_placed_order_is_never_placed_twice():
    placer, repo, adapter = _placer()
    order = _grocery_order()
    repo.add(order)
    placer.place(order)
    assert len(adapter.orders) == 1

    assert placer.place(order) is None
    assert len(adapter.orders) == 1


# --------------------------------------------------------------------------------------------------
# SKU resolution and placement
# --------------------------------------------------------------------------------------------------


def test_line_items_are_resolved_to_provider_skus_by_searching():
    placer, repo, adapter = _placer()
    order = _grocery_order()
    repo.add(order)

    placer.place(order)

    request = adapter.orders[0]
    assert request.provider_id == PROVIDER_ID
    assert request.reference == str(order.id)
    assert request.zip_code == "06600"
    assert [line.sku for line in request.lines] == ["fb-milk-1l", "fb-eggs-12"]


def test_out_of_stock_products_are_skipped_rather_than_ordered():
    placer, repo, adapter = _placer()
    order = _grocery_order()
    repo.add(order)

    placer.place(order)

    # The catalogue's bread is out of stock, so no line references it.
    assert all(line.sku != "fb-bread-wg" for line in adapter.orders[0].lines)


def test_quantities_are_whole_units_rounded_up_from_servings():
    placer, repo, adapter = _placer()
    order = _grocery_order()
    order.items[0].quantity = Decimal("1.2")
    repo.add(order)

    placer.place(order)

    quantities = {line.sku: line.quantity for line in adapter.orders[0].lines}
    assert quantities["fb-milk-1l"] == 2
    assert quantities["fb-eggs-12"] == 2


def test_a_placement_is_recorded_and_persisted():
    placer, repo, adapter = _placer()
    order = _grocery_order()
    repo.add(order)

    persisted = placer.place(order)

    assert persisted is not None
    assert persisted.grocery_external_order_id == order.grocery_external_order_id
    assert order.grocery_external_order_id.startswith(f"{PROVIDER_ID}_ord_")
    assert repo.get(order.id, user_id=USER_ID).is_placed_with_provider is True


def test_an_order_the_provider_cannot_supply_at_all_is_left_unplaced():
    placer, repo, adapter = _placer(FakeGroceryProviderAdapter(PROVIDER_ID, catalogue={}))
    order = _grocery_order()
    repo.add(order)

    assert placer.place(order) is None
    assert adapter.orders == []
    assert order.is_placed_with_provider is False


def test_a_provider_outage_never_fails_a_committed_order():
    repo = InMemoryOrderRepository()
    placer = GroceryOrderPlacer(
        repo, {PROVIDER_ID: _FailingGroceryAdapter()}, InMemoryEventPublisher()
    )
    order = _grocery_order()
    repo.add(order)

    assert placer.place(order) is None
    assert order.is_placed_with_provider is False
    assert order.status is OrderStatus.CONFIRMED


# --------------------------------------------------------------------------------------------------
# Confirm path 1: inline card charge at checkout (COM-202)
# --------------------------------------------------------------------------------------------------


def _create_service(
    adapter: FakeGroceryProviderAdapter,
) -> tuple[CreateOrderService, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    service = CreateOrderService(
        repo,
        FakeMealPlanProvider(_snapshot()),
        make_test_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
        None,
        None,
        GroceryOrderPlacer(repo, {PROVIDER_ID: adapter}, InMemoryEventPublisher()),
    )
    return service, repo


def _create_command(*, card: bool = True) -> CreateOrderCommand:
    return CreateOrderCommand(
        user_id=USER_ID,
        meal_plan_id=PLAN_ID,
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=_address(),
        delivery_date=date(2026, 9, 10),
        delivery_time_slot="09:00-11:00",
        provider_id=PROVIDER_ID,
        payment_method_type=(PaymentMethodType.CREDIT_CARD if card else PaymentMethodType.OXXO),
        payment_token=CARD_TOKEN if card else None,
    )


def test_create_places_a_card_confirmed_grocery_order():
    adapter = FakeGroceryProviderAdapter(PROVIDER_ID)
    service, _ = _create_service(adapter)

    order = service.create(_create_command(), bearer_token=TOKEN)

    assert order.status is OrderStatus.CONFIRMED
    assert len(adapter.orders) == 1
    assert order.is_placed_with_provider is True


def test_create_does_not_place_an_order_awaiting_async_payment():
    adapter = FakeGroceryProviderAdapter(PROVIDER_ID)
    service, _ = _create_service(adapter)

    order = service.create(_create_command(card=False), bearer_token=TOKEN)

    assert order.status is OrderStatus.PENDING
    assert adapter.orders == []


# --------------------------------------------------------------------------------------------------
# Confirm path 2: asynchronous payment webhook (COM-206)
# --------------------------------------------------------------------------------------------------


def _webhook_service(
    adapter: FakeGroceryProviderAdapter,
) -> tuple[ProcessPaymentWebhookService, InMemoryOrderRepository]:
    repo = InMemoryOrderRepository()
    service = ProcessPaymentWebhookService(
        repo,
        FakePaymentProvider(webhook_secret=WEBHOOK_SECRET),
        InMemoryEventPublisher(),
        None,
        None,
        GroceryOrderPlacer(repo, {PROVIDER_ID: adapter}, InMemoryEventPublisher()),
    )
    return service, repo


def _signed(order_id: uuid.UUID) -> tuple[bytes, str]:
    payload = json.dumps(
        {
            "type": "payment.confirmed",
            "data": {"reference": str(order_id), "charge_id": "ch_1"},
        }
    ).encode("utf-8")
    signature = hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return payload, signature


def test_an_async_confirmation_places_the_grocery_order():
    adapter = FakeGroceryProviderAdapter(PROVIDER_ID)
    service, repo = _webhook_service(adapter)
    order = _grocery_order(confirmed=False)
    repo.add(order)
    payload, signature = _signed(order.id)

    settled = service.process(payload=payload, signature=signature)

    assert settled.status is OrderStatus.CONFIRMED
    assert settled.payment_status is PaymentStatus.SUCCEEDED
    assert len(adapter.orders) == 1
    assert settled.is_placed_with_provider is True


def test_a_redelivered_confirmation_does_not_order_the_groceries_twice():
    adapter = FakeGroceryProviderAdapter(PROVIDER_ID)
    service, repo = _webhook_service(adapter)
    order = _grocery_order(confirmed=False)
    repo.add(order)
    payload, signature = _signed(order.id)
    service.process(payload=payload, signature=signature)

    service.process(payload=payload, signature=signature)

    assert len(adapter.orders) == 1
