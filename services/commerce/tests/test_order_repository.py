import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem


def _make_order(user_id: uuid.UUID, *, status: OrderStatus = OrderStatus.PENDING) -> Order:
    order = Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(
            street="Av. Reforma 100",
            city="Ciudad de Mexico",
            state="CDMX",
            zip_code="06600",
            country="MX",
            apartment="4B",
            instructions="Ring the bell",
            user_id=user_id,
        ),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=status,
        provider_id="prov-1",
        subtotal=Money(Decimal("100.00")),
        delivery_fee=Money(Decimal("20.00")),
        total=Money(Decimal("120.00")),
        notes="Leave at door",
    )
    order.add_item(
        OrderItem(
            name="Protein Bowl",
            quantity=Decimal("2"),
            unit="unit",
            unit_price=Money(Decimal("50.00")),
            line_total=Money(Decimal("100.00")),
        )
    )
    return order


def test_add_and_get_round_trip(order_repo):
    user_id = uuid.uuid4()
    saved = order_repo.add(_make_order(user_id))

    fetched = order_repo.get(saved.id, user_id=user_id)

    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.status is OrderStatus.PENDING
    assert fetched.fulfillment_type is FulfillmentType.DARK_KITCHEN
    assert fetched.provider_id == "prov-1"
    assert fetched.subtotal == Money(Decimal("100.00"))
    assert fetched.delivery_fee == Money(Decimal("20.00"))
    assert fetched.total == Money(Decimal("120.00"))
    assert fetched.notes == "Leave at door"
    assert fetched.delivery_address.street == "Av. Reforma 100"
    assert fetched.delivery_address.apartment == "4B"
    assert len(fetched.items) == 1
    assert fetched.items[0].name == "Protein Bowl"
    assert fetched.items[0].quantity == Decimal("2")
    assert fetched.items[0].unit_price == Money(Decimal("50.00"))
    assert fetched.items[0].line_total == Money(Decimal("100.00"))


def test_get_is_scoped_to_owner(order_repo):
    owner = uuid.uuid4()
    other = uuid.uuid4()
    saved = order_repo.add(_make_order(owner))

    assert order_repo.get(saved.id, user_id=other) is None


def test_get_unknown_returns_none(order_repo):
    assert order_repo.get(uuid.uuid4(), user_id=uuid.uuid4()) is None


def test_list_returns_only_owner_orders(order_repo):
    owner = uuid.uuid4()
    other = uuid.uuid4()
    order_repo.add(_make_order(owner))
    order_repo.add(_make_order(owner))
    order_repo.add(_make_order(other))

    orders = order_repo.list_for_user(owner)

    assert len(orders) == 2
    assert all(order.user_id == owner for order in orders)


def test_list_filters_by_status(order_repo):
    owner = uuid.uuid4()
    order_repo.add(_make_order(owner, status=OrderStatus.PENDING))
    order_repo.add(_make_order(owner, status=OrderStatus.DELIVERED))

    delivered = order_repo.list_for_user(owner, status=OrderStatus.DELIVERED)

    assert len(delivered) == 1
    assert delivered[0].status is OrderStatus.DELIVERED


def test_list_filters_by_from_date(order_repo):
    owner = uuid.uuid4()
    order_repo.add(_make_order(owner))
    today = datetime.now(UTC).date()

    assert len(order_repo.list_for_user(owner, from_date=today)) == 1
    assert len(order_repo.list_for_user(owner, from_date=today + timedelta(days=1))) == 0
