"""COM-408: provider fulfilment status is mapped onto our order states (AC2).

Covers the *inbound* half of grocery fulfilment: a provider's own status vocabulary is translated by
the COM-402 anti-corruption layer into the canonical
:class:`~app.domain.grocery_catalog.GroceryOrderStatus`, and this story maps that onto the COM-106
order lifecycle. A poll that jumps several statuses ahead walks the order forward one legal
transition at a time, so every intermediate state is timestamped in the history and publishes an
``order.status_changed`` event (COM-109). A status at or behind the order's own is a silent no-op,
which makes repeated polling idempotent and means a provider can never drag an order backwards.

Everything runs offline via in-memory doubles.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.application.queries import SyncGroceryOrderQuery
from app.application.sync_grocery_order import SyncGroceryOrderStatusService
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.errors import (
    GroceryOrderNotPlacedError,
    GroceryProviderUnavailableError,
    IllegalOrderTransitionError,
    OrderNotFoundError,
)
from app.domain.grocery_catalog import GroceryOrderStatus
from app.domain.grocery_fulfillment import order_status_for, steps_between
from app.domain.meal_plan import PlannedMeal
from app.domain.order import Order
from app.events.memory import InMemoryEventPublisher
from app.grocery.fake import FakeGroceryProviderAdapter
from app.main import app
from tests.fakes import InMemoryOrderRepository, StubVerifier, make_test_pricer

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
TOKEN = "caller-token"
PROVIDER_ID = "freshbasket"


def _address() -> Address:
    return Address(
        street="Av. Reforma 100", city="CDMX", state="CDMX", zip_code="06600", country="MX"
    )


def _placed_order(*, user_id: uuid.UUID = USER_ID, external_order_id: str = "fb_ord_1") -> Order:
    """A confirmed grocery order already placed with its provider."""
    order = Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=_address(),
        delivery_date=date(2026, 9, 10),
        delivery_time_slot="09:00-11:00",
        provider_id=PROVIDER_ID,
    )
    order.add_item(
        make_test_pricer().price_item(
            PlannedMeal(meal_type="breakfast", servings=Decimal("1"), recipe_name="Milk")
        )
    )
    order.confirm()
    order.record_grocery_placement(
        external_order_id=external_order_id, status=GroceryOrderStatus.PENDING
    )
    order.pull_events()
    return order


class _UnavailableAdapter:
    """An adapter whose status poll always fails, to prove the caller sees a 503."""

    provider_id = PROVIDER_ID

    def search(self, query):  # noqa: ANN001, ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)

    def place_order(self, request):  # noqa: ANN001, ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)

    def get_order_status(self, external_order_id: str):  # noqa: ANN201 - test double
        raise GroceryProviderUnavailableError(PROVIDER_ID)


# --------------------------------------------------------------------------------------------------
# Domain: the mapping table (AC2)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [
        (GroceryOrderStatus.PENDING, None),
        (GroceryOrderStatus.CONFIRMED, OrderStatus.CONFIRMED),
        (GroceryOrderStatus.PREPARING, OrderStatus.PREPARING),
        (GroceryOrderStatus.OUT_FOR_DELIVERY, OrderStatus.IN_TRANSIT),
        (GroceryOrderStatus.DELIVERED, OrderStatus.DELIVERED),
        (GroceryOrderStatus.CANCELLED, OrderStatus.CANCELLED),
        (GroceryOrderStatus.FAILED, OrderStatus.CANCELLED),
        (GroceryOrderStatus.UNKNOWN, None),
    ],
)
def test_every_provider_status_maps_to_an_order_state(provider_status, expected):
    assert order_status_for(provider_status) is expected


def test_the_mapping_covers_the_whole_provider_vocabulary():
    # A new provider status must be mapped deliberately, never fall through silently.
    for status in GroceryOrderStatus:
        order_status_for(status)


def test_steps_walks_the_order_forward_one_transition_at_a_time():
    assert steps_between(OrderStatus.CONFIRMED, OrderStatus.DELIVERED) == (
        OrderStatus.PREPARING,
        OrderStatus.IN_TRANSIT,
        OrderStatus.DELIVERED,
    )


def test_a_status_at_or_behind_the_order_needs_no_steps():
    assert steps_between(OrderStatus.IN_TRANSIT, OrderStatus.IN_TRANSIT) == ()
    assert steps_between(OrderStatus.IN_TRANSIT, OrderStatus.CONFIRMED) == ()


# --------------------------------------------------------------------------------------------------
# Domain: Order.apply_grocery_status
# --------------------------------------------------------------------------------------------------


def test_applying_a_status_records_the_provider_status():
    order = _placed_order()

    order.apply_grocery_status(GroceryOrderStatus.PREPARING)

    assert order.grocery_status is GroceryOrderStatus.PREPARING


def test_a_status_jump_records_every_intermediate_transition():
    order = _placed_order()
    already = len(order.status_history)

    order.apply_grocery_status(GroceryOrderStatus.DELIVERED)

    assert order.status is OrderStatus.DELIVERED
    assert [change.to_status for change in order.status_history[already:]] == [
        OrderStatus.PREPARING,
        OrderStatus.IN_TRANSIT,
        OrderStatus.DELIVERED,
    ]
    assert len(order.pull_events()) == 3


def test_repeating_a_status_is_idempotent():
    order = _placed_order()
    already = len(order.status_history)
    order.apply_grocery_status(GroceryOrderStatus.PREPARING)
    order.pull_events()

    order.apply_grocery_status(GroceryOrderStatus.PREPARING)

    assert len(order.status_history) == already + 1
    assert order.pull_events() == []


def test_a_stale_status_never_drags_the_order_backwards():
    order = _placed_order()
    order.apply_grocery_status(GroceryOrderStatus.OUT_FOR_DELIVERY)
    order.pull_events()

    order.apply_grocery_status(GroceryOrderStatus.CONFIRMED)

    assert order.status is OrderStatus.IN_TRANSIT
    assert order.pull_events() == []


def test_an_unmapped_status_leaves_the_lifecycle_alone():
    order = _placed_order()
    already = len(order.status_history)

    order.apply_grocery_status(GroceryOrderStatus.UNKNOWN)

    assert order.status is OrderStatus.CONFIRMED
    assert order.grocery_status is GroceryOrderStatus.UNKNOWN
    assert len(order.status_history) == already


def test_a_failed_provider_order_cancels_ours():
    order = _placed_order()

    order.apply_grocery_status(GroceryOrderStatus.FAILED)

    assert order.status is OrderStatus.CANCELLED


def test_cancelling_an_already_cancelled_order_is_a_no_op():
    order = _placed_order()
    order.apply_grocery_status(GroceryOrderStatus.CANCELLED)
    order.pull_events()

    order.apply_grocery_status(GroceryOrderStatus.CANCELLED)

    assert order.status is OrderStatus.CANCELLED
    assert order.pull_events() == []


def test_a_cancellation_of_a_dispatched_order_is_rejected():
    order = _placed_order()
    order.apply_grocery_status(GroceryOrderStatus.OUT_FOR_DELIVERY)

    with pytest.raises(IllegalOrderTransitionError):
        order.apply_grocery_status(GroceryOrderStatus.CANCELLED)


# --------------------------------------------------------------------------------------------------
# Use case: SyncGroceryOrderStatusService
# --------------------------------------------------------------------------------------------------


def _service(
    adapter=None,
) -> tuple[SyncGroceryOrderStatusService, InMemoryOrderRepository, InMemoryEventPublisher]:
    repo = InMemoryOrderRepository()
    publisher = InMemoryEventPublisher()
    adapters = {PROVIDER_ID: adapter or FakeGroceryProviderAdapter(PROVIDER_ID)}
    return SyncGroceryOrderStatusService(repo, adapters, publisher), repo, publisher


def test_sync_applies_the_providers_status_and_persists_it():
    service, repo, publisher = _service()
    order = _placed_order(external_order_id="fb_ord_1:picking")
    repo.add(order)

    synced = service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))

    assert synced.status is OrderStatus.PREPARING
    assert synced.grocery_status is GroceryOrderStatus.PREPARING
    assert repo.get(order.id, user_id=USER_ID).status is OrderStatus.PREPARING
    assert len(publisher.published) == 1


def test_sync_publishes_nothing_when_the_status_has_not_moved():
    service, repo, publisher = _service()
    order = _placed_order(external_order_id="fb_ord_1:created")
    repo.add(order)

    service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))

    assert publisher.published == []


def test_sync_of_an_unknown_order_is_not_found():
    service, _, _ = _service()

    with pytest.raises(OrderNotFoundError):
        service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=uuid.uuid4()))


def test_sync_of_another_users_order_is_not_found():
    service, repo, _ = _service()
    order = _placed_order(user_id=OTHER_USER_ID)
    repo.add(order)

    with pytest.raises(OrderNotFoundError):
        service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))


def test_sync_of_an_unplaced_order_is_a_conflict():
    service, repo, _ = _service()
    order = _placed_order()
    order.grocery_external_order_id = None
    repo.add(order)

    with pytest.raises(GroceryOrderNotPlacedError):
        service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))


def test_sync_of_an_order_whose_provider_has_no_adapter_is_a_conflict():
    service, repo, _ = _service()
    order = _placed_order()
    order.provider_id = "chedraui"
    repo.add(order)

    with pytest.raises(GroceryOrderNotPlacedError):
        service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))


def test_sync_surfaces_a_provider_outage():
    service, repo, _ = _service(_UnavailableAdapter())
    order = _placed_order()
    repo.add(order)

    with pytest.raises(GroceryProviderUnavailableError):
        service.sync(SyncGroceryOrderQuery(user_id=USER_ID, order_id=order.id))


# --------------------------------------------------------------------------------------------------
# HTTP: POST /orders/{orderId}/grocery/sync
# --------------------------------------------------------------------------------------------------


def _client(service: SyncGroceryOrderStatusService) -> TestClient:
    app.dependency_overrides[deps.get_token_verifier] = lambda: StubVerifier(
        {TOKEN: Principal(user_id=str(USER_ID), email="user@example.com")}
    )
    app.dependency_overrides[deps.get_sync_grocery_order_service] = lambda: service
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {TOKEN}"})
    return client


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(deps.get_token_verifier, None)
    app.dependency_overrides.pop(deps.get_sync_grocery_order_service, None)


def test_api_sync_returns_the_updated_order_with_its_grocery_block():
    service, repo, _ = _service()
    order = _placed_order(external_order_id="fb_ord_1:dispatched")
    repo.add(order)

    response = _client(service).post(f"/orders/{order.id}/grocery/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_transit"
    assert body["groceryOrder"] == {
        "providerId": PROVIDER_ID,
        "externalOrderId": "fb_ord_1:dispatched",
        "status": "out_for_delivery",
    }


def test_api_sync_requires_a_bearer_token():
    service, repo, _ = _service()
    order = _placed_order()
    repo.add(order)
    client = _client(service)
    client.headers.pop("Authorization")

    response = client.post(f"/orders/{order.id}/grocery/sync")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_api_sync_of_an_unknown_order_is_404():
    service, _, _ = _service()

    response = _client(service).post(f"/orders/{uuid.uuid4()}/grocery/sync")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_api_sync_of_an_unplaced_order_is_409():
    service, repo, _ = _service()
    order = _placed_order()
    order.grocery_external_order_id = None
    repo.add(order)

    response = _client(service).post(f"/orders/{order.id}/grocery/sync")

    assert response.status_code == 409


def test_api_sync_reports_a_provider_outage_as_503():
    service, repo, _ = _service(_UnavailableAdapter())
    order = _placed_order()
    repo.add(order)

    response = _client(service).post(f"/orders/{order.id}/grocery/sync")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")


def test_an_unplaced_order_carries_no_grocery_block():
    from app.api.schemas import OrderResponse

    order = _placed_order()
    order.grocery_external_order_id = None
    order.grocery_status = None

    assert OrderResponse.from_order(order).grocery_order is None
