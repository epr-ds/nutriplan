"""COM-806: golden pricing fixtures, checked at every level that prices an order.

``tests/golden/pricing.json`` holds the shipped rate card and a set of priced scenarios: line
totals, subtotal, delivery fee and total, including the free-delivery threshold and the rounding
rule (ROUND_HALF_UP per line, subtotal = sum of the rounded lines). Each scenario is checked
through the pricer, through order creation (so the order placed costs what the quote said) and on
the wire of ``POST /orders/quote`` (amounts and formatted strings), so a pricing change anywhere
has to change the golden file on purpose.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quote_order_service, get_token_verifier
from app.application.commands import CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.application.quote_order import QuoteOrderService
from app.core.config import Settings
from app.core.principal import Principal
from app.domain.address import Address
from app.domain.enums import FulfillmentType
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.money import Money
from app.domain.order import OrderItem
from app.domain.pricing import DeliveryFeeSchedule, MealTypePriceBook, OrderPricer
from app.events.memory import InMemoryEventPublisher
from app.main import app
from app.payments.fake import FakePaymentProvider
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    StubVerifier,
)

_GOLDEN = json.loads((Path(__file__).parent / "golden" / "pricing.json").read_text("utf-8"))
_RATE_CARD: dict[str, Any] = _GOLDEN["rateCard"]
_SCENARIOS: list[dict[str, Any]] = _GOLDEN["scenarios"]
_IDS = [scenario["name"] for scenario in _SCENARIOS]

TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="golden@example.com")
PLAN_ID = str(uuid.uuid4())
_AUTH = {"Authorization": f"Bearer {TOKEN}"}
_CENTS = Decimal("0.01")
_ADDRESS = Address(street="Reforma 222", city="CDMX", state="CDMX", zip_code="06600", country="MX")


def _mxn(value: str) -> Money:
    return Money(Decimal(value))


def _golden_pricer() -> OrderPricer:
    """The real pricer, configured with the golden rate card."""
    per_serving = _RATE_CARD["perServing"]
    rates = {kind: _mxn(rate) for kind, rate in per_serving.items() if kind != "default"}
    fees = {FulfillmentType(kind): _mxn(fee) for kind, fee in _RATE_CARD["deliveryFee"].items()}
    threshold = _mxn(_RATE_CARD["freeDeliveryThreshold"])
    return OrderPricer(
        MealTypePriceBook(rates=rates, default_rate=_mxn(per_serving["default"])),
        DeliveryFeeSchedule(fees=fees, free_delivery_threshold=threshold),
    )


def _snapshot(scenario: dict[str, Any]) -> MealPlanSnapshot:
    meals = [
        PlannedMeal(meal["mealType"], Decimal(meal["servings"]), meal["recipeName"])
        for meal in scenario["meals"]
    ]
    return MealPlanSnapshot(plan_id=PLAN_ID, meals=meals)


def _assert_priced(
    items: list[OrderItem], subtotal: Money, fee: Money, total: Money, expected: dict[str, Any]
) -> None:
    lines = expected["items"]
    actual = [(item.name, item.unit_price, item.line_total) for item in items]
    golden = [(line["name"], _mxn(line["unitPrice"]), _mxn(line["lineTotal"])) for line in lines]
    assert actual == golden
    assert subtotal == _mxn(expected["subtotal"])
    assert fee == _mxn(expected["deliveryFee"])
    assert total == _mxn(expected["total"])
    assert total.formatted == expected["formattedTotal"]


# --- the golden file itself -----------------------------------------------------------------------


def test_the_golden_rate_card_is_the_shipped_one():
    """The goldens price with the service's default rate card; a new price must update them."""
    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    for meal_type, rate in _RATE_CARD["perServing"].items():
        assert defaults[f"price_per_serving_{meal_type}"] == Decimal(rate), meal_type
    for kind, fee in _RATE_CARD["deliveryFee"].items():
        assert defaults[f"delivery_fee_{kind}"] == Decimal(fee), kind
    assert defaults["free_delivery_threshold"] == Decimal(_RATE_CARD["freeDeliveryThreshold"])
    assert defaults["default_currency"] == "MXN"


def test_every_fulfillment_type_has_a_golden_scenario():
    covered = {scenario["fulfillmentType"] for scenario in _SCENARIOS}

    assert covered == {kind.value for kind in FulfillmentType}


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_the_golden_figures_add_up(scenario: dict[str, Any]):
    """Guard the fixture: two-decimal amounts, lines that sum to the subtotal, fee + subtotal."""
    expected = scenario["expected"]
    lines = [Decimal(line["lineTotal"]) for line in expected["items"]]
    subtotal = Decimal(expected["subtotal"])
    fee = Decimal(expected["deliveryFee"])
    total = Decimal(expected["total"])

    assert all(amount == amount.quantize(_CENTS) for amount in [*lines, subtotal, fee, total])
    assert sum(lines) == subtotal
    assert subtotal + fee == total


# --- the pricer -----------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_the_quote_matches_the_golden(scenario: dict[str, Any]):
    kind = FulfillmentType(scenario["fulfillmentType"])
    expected = scenario["expected"]

    quote = _golden_pricer().quote(_snapshot(scenario).meals, kind)

    _assert_priced(quote.items, quote.subtotal, quote.delivery_fee, quote.total, expected)


# --- the order placed -----------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_the_order_placed_matches_the_golden(scenario: dict[str, Any]):
    kind = FulfillmentType(scenario["fulfillmentType"])
    expected = scenario["expected"]
    service = CreateOrderService(
        InMemoryOrderRepository(),
        FakeMealPlanProvider(_snapshot(scenario)),
        _golden_pricer(),
        InMemoryEventPublisher(),
        FakePaymentProvider(),
        InMemoryIdempotencyStore(),
    )
    command = CreateOrderCommand(
        user_id=uuid.UUID(PRINCIPAL.user_id),
        meal_plan_id=PLAN_ID,
        fulfillment_type=kind,
        delivery_address=_ADDRESS,
        delivery_date=date(2026, 11, 2),
        delivery_time_slot="13:00-15:00",
        provider_id="freshbasket" if kind is FulfillmentType.GROCERY_DELIVERY else None,
    )

    order = service.create(command, bearer_token=TOKEN)

    assert order.subtotal is not None
    assert order.delivery_fee is not None
    assert order.total is not None
    _assert_priced(order.items, order.subtotal, order.delivery_fee, order.total, expected)


# --- the wire -------------------------------------------------------------------------------------


@pytest.fixture
def client():
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({TOKEN: PRINCIPAL})
    yield TestClient(app)
    app.dependency_overrides.pop(get_token_verifier, None)
    app.dependency_overrides.pop(get_quote_order_service, None)


def _wire(amount: str) -> dict[str, Any]:
    """A golden amount as ``MoneyResponse`` puts it on the wire."""
    money = _mxn(amount)
    return {"amount": float(money.amount), "currency": "MXN", "formatted": money.formatted}


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_the_quote_on_the_wire_matches_the_golden(client: TestClient, scenario: dict[str, Any]):
    kind = scenario["fulfillmentType"]
    expected = scenario["expected"]
    service = QuoteOrderService(FakeMealPlanProvider(_snapshot(scenario)), _golden_pricer())
    app.dependency_overrides[get_quote_order_service] = lambda: service
    body = {"mealPlanId": PLAN_ID, "fulfillmentType": kind}
    if kind == FulfillmentType.GROCERY_DELIVERY.value:
        body["providerId"] = "freshbasket"

    response = client.post("/commerce/v1/orders/quote", json=body, headers=_AUTH)

    assert response.status_code == 200, response.text
    quote = response.json()
    lines = expected["items"]
    actual = [(item["name"], item["unitPrice"], item["lineTotal"]) for item in quote["items"]]
    golden = [(line["name"], _wire(line["unitPrice"]), _wire(line["lineTotal"])) for line in lines]
    assert actual == golden
    assert quote["subtotal"] == _wire(expected["subtotal"])
    assert quote["deliveryFee"] == _wire(expected["deliveryFee"])
    assert quote["total"] == _wire(expected["total"])
    assert quote["total"]["formatted"] == expected["formattedTotal"]
