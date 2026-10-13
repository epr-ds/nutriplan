"""COM-103 unit tests for the pricing engine (pure domain, no DB/network).

Covers the three acceptance criteria: subtotal/deliveryFee/total in MXN, per-fulfillmentType
delivery-fee rules (incl. a free-delivery threshold), and the rounding rule (ROUND_HALF_UP per line,
subtotal = sum of already-rounded line totals).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.address import Address
from app.domain.enums import FulfillmentType
from app.domain.meal_plan import PlannedMeal
from app.domain.money import Money
from app.domain.order import Order, OrderItem
from app.domain.pricing import DeliveryFeeSchedule, MealTypePriceBook, OrderPricer


def _mxn(value: str) -> Money:
    return Money(Decimal(value))


PRICE_BOOK = MealTypePriceBook(
    rates={
        "breakfast": _mxn("10.00"),
        "lunch": _mxn("20.00"),
        "dinner": _mxn("30.00"),
        "snack": _mxn("5.00"),
    },
    default_rate=_mxn("15.00"),
)

FEES = DeliveryFeeSchedule(
    fees={
        FulfillmentType.DARK_KITCHEN: _mxn("35.00"),
        FulfillmentType.GROCERY_DELIVERY: _mxn("49.00"),
        FulfillmentType.PICKUP: _mxn("0.00"),
    },
    free_delivery_threshold=_mxn("100.00"),
)


def _order(fulfillment_type: FulfillmentType, items: list[OrderItem]) -> Order:
    return Order(
        user_id=uuid.uuid4(),
        fulfillment_type=fulfillment_type,
        delivery_address=Address(street="s", city="c", state="st", zip_code="00000", country="MX"),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        items=list(items),
    )


# --- PriceBook --------------------------------------------------------------------------------


def test_price_book_returns_rate_for_known_meal_type():
    assert PRICE_BOOK.unit_price("lunch") == _mxn("20.00")


def test_price_book_is_case_insensitive():
    assert PRICE_BOOK.unit_price("BREAKFAST") == _mxn("10.00")


def test_price_book_falls_back_to_default_for_unknown_type():
    assert PRICE_BOOK.unit_price("brunch") == _mxn("15.00")


# --- item pricing -----------------------------------------------------------------------------


def test_price_item_sets_unit_price_and_line_total():
    pricer = OrderPricer(PRICE_BOOK, FEES)
    item = pricer.price_item(
        PlannedMeal(meal_type="dinner", servings=Decimal("2"), recipe_name="Salmon")
    )
    assert item.name == "Salmon"
    assert item.quantity == Decimal("2")
    assert item.unit == "serving"
    assert item.unit_price == _mxn("30.00")
    assert item.line_total == _mxn("60.00")


def test_price_item_name_falls_back_to_meal_type_label():
    pricer = OrderPricer(PRICE_BOOK, FEES)
    item = pricer.price_item(
        PlannedMeal(meal_type="grain_bowl", servings=Decimal("1"), recipe_name=None)
    )
    assert item.name == "Grain Bowl"
    assert item.unit_price == _mxn("15.00")  # default rate


# --- order totals -----------------------------------------------------------------------------


def test_price_order_computes_subtotal_fee_and_total():
    pricer = OrderPricer(PRICE_BOOK, FEES)
    order = _order(
        FulfillmentType.DARK_KITCHEN,
        [
            pricer.price_item(PlannedMeal(meal_type="breakfast", servings=Decimal("1"))),
            pricer.price_item(PlannedMeal(meal_type="snack", servings=Decimal("2"))),
        ],
    )

    pricer.price_order(order)

    assert order.subtotal == _mxn("20.00")  # 10 + (5 * 2)
    assert order.delivery_fee == _mxn("35.00")
    assert order.total == _mxn("55.00")


def test_empty_order_has_zero_subtotal_but_still_incurs_delivery_fee():
    pricer = OrderPricer(PRICE_BOOK, FEES)
    order = _order(FulfillmentType.DARK_KITCHEN, [])
    pricer.price_order(order)
    assert order.subtotal == Money.zero()
    assert order.total == _mxn("35.00")


# --- delivery-fee rules -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fulfillment_type", "expected"),
    [
        (FulfillmentType.DARK_KITCHEN, "35.00"),
        (FulfillmentType.GROCERY_DELIVERY, "49.00"),
        (FulfillmentType.PICKUP, "0.00"),
    ],
)
def test_delivery_fee_per_fulfillment_type(fulfillment_type: FulfillmentType, expected: str):
    assert FEES.fee_for(fulfillment_type, _mxn("50.00")) == _mxn(expected)


def test_free_delivery_at_or_above_threshold():
    assert FEES.fee_for(FulfillmentType.DARK_KITCHEN, _mxn("100.00")) == Money.zero()
    assert FEES.fee_for(FulfillmentType.GROCERY_DELIVERY, _mxn("250.00")) == Money.zero()


def test_fee_applies_just_below_threshold():
    assert FEES.fee_for(FulfillmentType.DARK_KITCHEN, _mxn("99.99")) == _mxn("35.00")


def test_pickup_is_free_regardless_of_subtotal():
    assert FEES.fee_for(FulfillmentType.PICKUP, _mxn("5.00")) == Money.zero()
    assert FEES.fee_for(FulfillmentType.PICKUP, _mxn("500.00")) == Money.zero()


# --- rounding ---------------------------------------------------------------------------------


def test_line_total_rounds_half_up():
    pricer = OrderPricer(
        MealTypePriceBook(rates={"dinner": _mxn("3.33")}, default_rate=_mxn("3.33")), FEES
    )
    item = pricer.price_item(PlannedMeal(meal_type="dinner", servings=Decimal("1.5")))
    # 3.33 * 1.5 = 4.995 -> ROUND_HALF_UP to centavos -> 5.00
    assert item.line_total == _mxn("5.00")


def test_subtotal_is_sum_of_rounded_line_totals():
    # Each line is 0.05 * 1.5 = 0.075 -> rounds to 0.08; two lines sum to 0.16 (round-then-sum).
    # Summing raw amounts first (0.15) then rounding would give 0.15, so 0.16 locks the rule.
    pricer = OrderPricer(
        MealTypePriceBook(rates={"snack": _mxn("0.05")}, default_rate=_mxn("0.05")), FEES
    )
    order = _order(
        FulfillmentType.PICKUP,
        [
            pricer.price_item(PlannedMeal(meal_type="snack", servings=Decimal("1.5"))),
            pricer.price_item(PlannedMeal(meal_type="snack", servings=Decimal("1.5"))),
        ],
    )
    pricer.price_order(order)
    assert order.items[0].line_total == _mxn("0.08")
    assert order.subtotal == _mxn("0.16")
    assert order.total == _mxn("0.16")  # pickup is free
