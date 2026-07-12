import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update

from app.db.models import OrderModel
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


def _stamp_created_at(order_repo, order_id, when):
    order_repo._db.execute(
        update(OrderModel).where(OrderModel.id == order_id).values(created_at=when)
    )
    order_repo._db.commit()
    order_repo._db.expire_all()  # drop identity-map cache so the next read reflects the new value


def test_list_returns_newest_first(order_repo):
    owner = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    older = order_repo.add(_make_order(owner)).id
    newer = order_repo.add(_make_order(owner)).id
    _stamp_created_at(order_repo, older, base)
    _stamp_created_at(order_repo, newer, base + timedelta(days=1))

    ids = [order.id for order in order_repo.list_for_user(owner)]

    assert ids == [newer, older]


def test_list_paginates_with_limit_and_offset(order_repo):
    owner = uuid.uuid4()
    all_ids = {order_repo.add(_make_order(owner)).id for _ in range(3)}

    page1 = order_repo.list_for_user(owner, limit=2, offset=0)
    page2 = order_repo.list_for_user(owner, limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 1
    page1_ids = {order.id for order in page1}
    page2_ids = {order.id for order in page2}
    assert page1_ids.isdisjoint(page2_ids)  # stable order → no overlap across pages
    assert page1_ids | page2_ids == all_ids


def test_list_combines_status_filter_with_pagination(order_repo):
    owner = uuid.uuid4()
    for _ in range(3):
        order_repo.add(_make_order(owner, status=OrderStatus.DELIVERED))
    order_repo.add(_make_order(owner, status=OrderStatus.PENDING))

    delivered = order_repo.list_for_user(owner, status=OrderStatus.DELIVERED, limit=2)

    assert len(delivered) == 2
    assert all(order.status is OrderStatus.DELIVERED for order in delivered)
