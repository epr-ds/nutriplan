"""Seed and teardown helpers for tests that run against a real database (COM-801).

The harness fixtures in ``conftest.py`` (``seeded_orders``, ``seeded_payment_methods``) use these
builders, and any test (repository, API, provider contract or integration) can call them directly
with a session. Everything is written through the service's own repositories
(:class:`SqlOrderRepository`, :class:`SqlPaymentMethodRepository`) and domain objects, so the rows
are exactly what the service would store.

Teardown comes in two strengths: :func:`drop_schema` / :func:`create_schema` rebuild the tables
(what the autouse ``_schema`` fixture does around every test), and :func:`clear_data` empties every
table in dependency order while keeping the schema, for a test that wants a clean slate mid-way.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.grocery_catalog import GroceryOrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem
from app.domain.payment_method import SavedPaymentMethod
from app.repositories.sql_order_repository import SqlOrderRepository
from app.repositories.sql_payment_method_repository import SqlPaymentMethodRepository

#: The owner of the seeded data; API tests authenticate as this user.
SEED_USER_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")

#: The day every seeded order is delivered on.
SEED_DELIVERY_DATE = date(2026, 11, 2)


# --- teardown ---------------------------------------------------------------------------------


def create_schema(engine: Engine) -> None:
    """Create every table the service maps (no-op for tables that already exist)."""
    Base.metadata.create_all(bind=engine)


def drop_schema(engine: Engine) -> None:
    """Drop every table the service maps, leaving an empty database."""
    Base.metadata.drop_all(bind=engine)


def clear_data(session: Session) -> None:
    """Delete every row, children before parents, and commit; the schema is kept."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


# --- seed -------------------------------------------------------------------------------------


def _address(user_id: uuid.UUID) -> Address:
    return Address(
        street="Av. Reforma 222",
        city="Ciudad de Mexico",
        state="CDMX",
        zip_code="06600",
        country="MX",
        apartment="4B",
        user_id=user_id,
    )


def _item(name: str, quantity: str, unit_price: str) -> OrderItem:
    price = Decimal(unit_price)
    return OrderItem(
        name=name,
        quantity=Decimal(quantity),
        unit="serving",
        unit_price=Money(price),
        line_total=Money(price * Decimal(quantity)),
    )


def build_kitchen_order(user_id: uuid.UUID = SEED_USER_ID) -> Order:
    """A pending dark-kitchen order with two lines: 2 x 89.00 + 1 x 65.00, plus 30.00 delivery."""
    order = Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_address(user_id),
        delivery_date=SEED_DELIVERY_DATE,
        delivery_time_slot="13:00-14:00",
        status=OrderStatus.PENDING,
        provider_id="kitchen-roma",
        subtotal=Money(Decimal("243.00")),
        delivery_fee=Money(Decimal("30.00")),
        total=Money(Decimal("273.00")),
        notes="Harness kitchen order",
    )
    order.add_item(_item("Lentil soup", "2", "89.00"))
    order.add_item(_item("Protein bowl", "1", "65.00"))
    return order


def build_grocery_order(user_id: uuid.UUID = SEED_USER_ID) -> Order:
    """A confirmed grocery-delivery order already placed with FreshBasket."""
    order = Order(
        user_id=user_id,
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        delivery_address=_address(user_id),
        delivery_date=SEED_DELIVERY_DATE,
        delivery_time_slot="18:00-20:00",
        status=OrderStatus.CONFIRMED,
        provider_id="freshbasket",
        subtotal=Money(Decimal("150.00")),
        delivery_fee=Money(Decimal("45.00")),
        total=Money(Decimal("195.00")),
        grocery_external_order_id="FB-1001",
        grocery_status=GroceryOrderStatus.CONFIRMED,
    )
    order.add_item(_item("Rice 1 kg", "1", "50.00"))
    order.add_item(_item("Chicken breast 500 g", "2", "50.00"))
    return order


def seed_orders(session: Session, *, user_id: uuid.UUID = SEED_USER_ID) -> list[Order]:
    """Store the kitchen and grocery orders for *user_id* and return them (kitchen first)."""
    repository = SqlOrderRepository(session)
    return [
        repository.add(build_kitchen_order(user_id)),
        repository.add(build_grocery_order(user_id)),
    ]


def seed_payment_methods(
    session: Session, *, user_id: uuid.UUID = SEED_USER_ID
) -> list[SavedPaymentMethod]:
    """Store a saved Visa card and a PayPal wallet for *user_id* and return them (card first)."""
    repository = SqlPaymentMethodRepository(session)
    return [
        repository.add(
            SavedPaymentMethod(
                user_id=user_id,
                type=PaymentMethodType.CREDIT_CARD,
                token="tok_harness_visa",
                brand="visa",
                last4="4242",
                exp_month=12,
                exp_year=2030,
            )
        ),
        repository.add(
            SavedPaymentMethod(
                user_id=user_id, type=PaymentMethodType.PAYPAL, token="tok_harness_paypal"
            )
        ),
    ]
