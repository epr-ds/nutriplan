"""Pydantic response schemas projecting the ``Order`` aggregate onto the OpenAPI wire shapes.

All wire fields are camelCase. ``Money`` amounts project to JSON ``number`` (float) to match the
contract; the exact ``Decimal`` stays in the domain/storage layers.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, ProviderType
from app.domain.money import Money
from app.domain.order import Order, OrderItem


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AddressRequest(_Camel):
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    apartment: str | None = None
    instructions: str | None = None

    def to_domain(self) -> Address:
        return Address(
            street=self.street,
            city=self.city,
            state=self.state,
            zip_code=self.zip_code,
            country=self.country,
            apartment=self.apartment,
            instructions=self.instructions,
        )


class PaymentMethodRequest(_Camel):
    type: str
    token: str


class CreateOrderRequest(_Camel):
    meal_plan_id: uuid.UUID
    fulfillment_type: FulfillmentType
    delivery_address: AddressRequest
    delivery_date: date
    delivery_time_slot: str
    provider_id: str | None = None
    payment_method: PaymentMethodRequest | None = None
    notes: str | None = None


class MoneyResponse(_Camel):
    amount: float
    currency: str = "MXN"
    formatted: str

    @classmethod
    def from_money(cls, money: Money) -> MoneyResponse:
        return cls(
            amount=float(money.amount),
            currency=money.currency,
            formatted=money.formatted,
        )


class OrderItemResponse(_Camel):
    name: str
    quantity: float
    unit: str
    unit_price: MoneyResponse
    line_total: MoneyResponse

    @classmethod
    def from_item(cls, item: OrderItem) -> OrderItemResponse:
        return cls(
            name=item.name,
            quantity=float(item.quantity),
            unit=item.unit,
            unit_price=MoneyResponse.from_money(item.unit_price),
            line_total=MoneyResponse.from_money(item.line_total),
        )


class ProviderResponse(_Camel):
    id: str | None = None
    name: str | None = None
    type: ProviderType | None = None
    logo_url: str | None = None
    estimated_delivery: str | None = None


class OrderResponse(_Camel):
    id: uuid.UUID
    status: OrderStatus
    fulfillment_type: FulfillmentType
    provider: ProviderResponse | None = None
    items: list[OrderItemResponse]
    subtotal: MoneyResponse
    delivery_fee: MoneyResponse
    total: MoneyResponse
    estimated_delivery: datetime | None = None
    tracking_url: str | None = None

    @classmethod
    def from_order(cls, order: Order) -> OrderResponse:
        provider = ProviderResponse(id=order.provider_id) if order.provider_id else None
        return cls(
            id=order.id,
            status=order.status,
            fulfillment_type=order.fulfillment_type,
            provider=provider,
            items=[OrderItemResponse.from_item(item) for item in order.items],
            subtotal=MoneyResponse.from_money(order.subtotal),
            delivery_fee=MoneyResponse.from_money(order.delivery_fee),
            total=MoneyResponse.from_money(order.total),
            estimated_delivery=order.estimated_delivery,
            tracking_url=order.tracking_url,
        )
