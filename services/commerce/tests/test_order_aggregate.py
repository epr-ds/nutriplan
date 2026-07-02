import uuid
from datetime import date
from decimal import Decimal

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem


def _address() -> Address:
    return Address(
        street="Av. Reforma 100",
        city="Ciudad de Mexico",
        state="CDMX",
        zip_code="06600",
        country="MX",
    )


def _order() -> Order:
    return Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
    )


def test_order_defaults():
    order = _order()
    assert order.status is OrderStatus.PENDING
    assert order.subtotal == Money.zero()
    assert order.delivery_fee == Money.zero()
    assert order.total == Money.zero()
    assert order.items == []
    assert order.provider_id is None
    assert isinstance(order.id, uuid.UUID)


def test_add_item_appends():
    order = _order()
    item = OrderItem(
        name="Protein Bowl",
        quantity=Decimal("2"),
        unit="unit",
        unit_price=Money(Decimal("50.00")),
        line_total=Money(Decimal("100.00")),
    )
    order.add_item(item)
    assert len(order.items) == 1
    assert order.items[0].name == "Protein Bowl"
    assert order.items[0].line_total == Money(Decimal("100.00"))


def test_order_carries_pricing_and_fulfillment():
    order = Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=_address(),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="18:00-19:00",
        status=OrderStatus.CONFIRMED,
        subtotal=Money(Decimal("200.00")),
        delivery_fee=Money(Decimal("35.00")),
        total=Money(Decimal("235.00")),
    )
    assert order.fulfillment_type is FulfillmentType.GROCERY_DELIVERY
    assert order.status is OrderStatus.CONFIRMED
    assert order.total == Money(Decimal("235.00"))
