from decimal import Decimal

import pytest

from app.domain.money import Money


def test_quantizes_to_two_places():
    assert Money(Decimal("10")).amount == Decimal("10.00")


def test_rounds_half_up():
    assert Money(Decimal("10.005")).amount == Decimal("10.01")


def test_default_currency_is_mxn():
    assert Money(Decimal("1")).currency == "MXN"


def test_formatted_with_thousands_separator():
    assert Money(Decimal("1234.5")).formatted == "$1,234.50 MXN"


def test_zero_factory():
    assert Money.zero().amount == Decimal("0.00")
    assert Money.zero("USD").currency == "USD"


def test_add_same_currency():
    assert (Money(Decimal("1.50")) + Money(Decimal("2.25"))).amount == Decimal("3.75")


def test_add_currency_mismatch_raises():
    with pytest.raises(ValueError):
        _ = Money(Decimal("1"), "MXN") + Money(Decimal("1"), "USD")


def test_multiply_by_int():
    assert (Money(Decimal("3.33")) * 3).amount == Decimal("9.99")


def test_multiply_by_decimal():
    assert (Money(Decimal("12.00")) * Decimal("1.5")).amount == Decimal("18.00")


def test_requires_currency():
    with pytest.raises(ValueError):
        Money(Decimal("1"), "")


def test_equality_and_hashable():
    assert Money(Decimal("5.00")) == Money(Decimal("5.00"))
    assert Money(Decimal("5.00"), "USD") != Money(Decimal("5.00"), "MXN")
    assert len({Money(Decimal("5.00")), Money(Decimal("5.00"))}) == 1
