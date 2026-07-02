"""COM-101: OrderResponse projects the aggregate onto the commerce.openapi.yaml shape.

Includes a contract drift-guard: the projected field names must be a subset of the properties
documented in ``contracts/commerce.openapi.yaml``. The guard skips locally when the spec is not
mounted, but hard-fails under CI so a mis-wired gate can't pass silently.
"""

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.schemas import OrderResponse
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem


def _order() -> Order:
    order = Order(
        user_id=uuid.uuid4(),
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=Address(
            street="Av. Reforma 100",
            city="Ciudad de Mexico",
            state="CDMX",
            zip_code="06600",
            country="MX",
        ),
        delivery_date=date(2026, 7, 10),
        delivery_time_slot="12:00-13:00",
        status=OrderStatus.CONFIRMED,
        provider_id="prov-1",
        subtotal=Money(Decimal("100.00")),
        delivery_fee=Money(Decimal("20.00")),
        total=Money(Decimal("120.00")),
        estimated_delivery=datetime(2026, 7, 10, 12, 30, tzinfo=UTC),
        tracking_url="https://track.example/abc",
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


def test_projection_field_values():
    data = OrderResponse.from_order(_order()).model_dump(by_alias=True)
    assert data["status"] == "confirmed"
    assert data["fulfillmentType"] == "dark_kitchen"
    assert data["total"]["amount"] == 120.0
    assert data["total"]["currency"] == "MXN"
    assert data["total"]["formatted"] == "$120.00 MXN"
    assert data["items"][0]["unitPrice"]["amount"] == 50.0
    assert data["items"][0]["quantity"] == 2.0
    assert data["provider"]["id"] == "prov-1"
    assert data["trackingUrl"] == "https://track.example/abc"


def test_money_amount_projects_as_json_number():
    data = OrderResponse.from_order(_order()).model_dump(by_alias=True)
    assert isinstance(data["total"]["amount"], float)
    assert isinstance(data["items"][0]["lineTotal"]["amount"], float)


def test_provider_null_when_absent():
    order = _order()
    order.provider_id = None
    data = OrderResponse.from_order(order).model_dump(by_alias=True)
    assert data["provider"] is None


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def test_projection_conforms_to_contract():
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    schemas = yaml.safe_load(spec_path.read_text(encoding="utf-8"))["components"]["schemas"]

    def documented(name: str) -> set[str]:
        return set(schemas[name].get("properties", {}).keys())

    data = OrderResponse.from_order(_order()).model_dump(by_alias=True)
    assert set(data.keys()) <= documented("OrderResponse")
    assert set(data["items"][0].keys()) <= documented("OrderItemResponse")
    assert set(data["total"].keys()) <= documented("MoneyResponse")
    assert set(data["provider"].keys()) <= documented("ProviderResponse")
