"""Pydantic response schemas projecting the ``Order`` aggregate onto the OpenAPI wire shapes.

All wire fields are camelCase. ``Money`` amounts project to JSON ``number`` (float) to match the
contract; the exact ``Decimal`` stays in the domain/storage layers.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.address import Address
from app.domain.enums import (
    FulfillmentType,
    OrderStatus,
    PaymentMethodType,
    ProviderType,
    RefundStatus,
)
from app.domain.fulfillment import DarkKitchenAvailability
from app.domain.grocery import GroceryProvider
from app.domain.grocery_catalog import GrocerySearchItem, GrocerySearchQuery
from app.domain.money import Money
from app.domain.order import Order, OrderItem
from app.domain.payment_method import SavedPaymentMethod


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
    type: PaymentMethodType
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


class CancelOrderRequest(_Camel):
    """Options for cancelling an order (COM-208).

    ``refundAmount`` requests a *partial* refund of a paid order; omit it (or send an empty body) to
    refund the order in full. A positive value no greater than the order total is required, else the
    request is rejected with ``422``. It is ignored when the order was never paid.
    """

    refund_amount: float | None = None


class GrocerySearchItemRequest(_Camel):
    """One requested ingredient line in a grocery search (mirrors the contract's ``items[]``)."""

    ingredient: str = Field(min_length=1)
    quantity: float | None = None
    unit: str | None = None


class GrocerySearchRequest(_Camel):
    """A product search across grocery providers (COM-403), mirroring ``GrocerySearchRequest``.

    ``items`` must carry at least one ingredient and ``zipCode`` must be a 5-digit Mexican postal
    code (else ``422``). ``providers`` optionally restricts the fan-out to specific provider ids;
    omitted or empty means every enabled provider.
    """

    items: list[GrocerySearchItemRequest] = Field(min_length=1)
    zip_code: str = Field(pattern=r"^\d{5}$")
    providers: list[str] = Field(default_factory=list)

    def to_query(self) -> GrocerySearchQuery:
        """Project the request onto the provider-agnostic domain query (COM-402)."""
        return GrocerySearchQuery(
            zip_code=self.zip_code,
            items=tuple(
                GrocerySearchItem(
                    ingredient=item.ingredient,
                    quantity=Decimal(str(item.quantity)) if item.quantity is not None else None,
                    unit=item.unit,
                )
                for item in self.items
            ),
            providers=tuple(self.providers),
        )


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

    @classmethod
    def from_domain(cls, provider: GroceryProvider) -> ProviderResponse:
        """Project a configured grocery provider onto the wire shape (COM-401)."""
        return cls(
            id=provider.id,
            name=provider.name,
            type=provider.type,
            logo_url=provider.logo_url,
            estimated_delivery=provider.estimated_delivery,
        )


class AvailabilityResponse(_Camel):
    """Dark-kitchen availability for a delivery area (COM-301), mirroring ``AvailabilityResponse``.

    ``timeSlots`` lists the delivery windows offered when ``available`` is true, and is empty
    otherwise.
    """

    available: bool
    zip_code: str
    time_slots: list[str]

    @classmethod
    def from_domain(cls, availability: DarkKitchenAvailability) -> AvailabilityResponse:
        return cls(
            available=availability.available,
            zip_code=availability.zip_code,
            time_slots=list(availability.time_slots),
        )


class VoucherResponse(_Camel):
    """An issued OXXO voucher for an async payment (COM-203); the order stays ``pending``."""

    reference: str
    amount: MoneyResponse
    expires_at: datetime
    provider: str | None = None
    barcode_url: str | None = None


class TransferResponse(_Camel):
    """Issued SPEI bank-transfer instructions (COM-204); the order stays ``pending``."""

    clabe: str
    reference: str
    amount: MoneyResponse
    expires_at: datetime
    provider: str | None = None


class ApprovalResponse(_Camel):
    """A created PayPal redirect-approval order (COM-205); the order stays ``pending``."""

    approval_url: str
    reference: str
    amount: MoneyResponse
    expires_at: datetime
    provider: str | None = None


class RefundResponse(_Camel):
    """A refund captured when a paid order was cancelled (COM-208).

    Present only once a paid order has actually been refunded. ``status`` is ``full`` when the whole
    total was returned or ``partial`` otherwise, and ``amount`` is the exact sum refunded.
    """

    refund_id: str
    status: RefundStatus
    amount: MoneyResponse
    provider: str | None = None


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
    voucher: VoucherResponse | None = None
    transfer: TransferResponse | None = None
    approval: ApprovalResponse | None = None
    refund: RefundResponse | None = None

    @classmethod
    def from_order(cls, order: Order) -> OrderResponse:
        provider = ProviderResponse(id=order.provider_id) if order.provider_id else None
        voucher = None
        if order.payment_voucher_reference is not None:
            voucher = VoucherResponse(
                reference=order.payment_voucher_reference,
                amount=MoneyResponse.from_money(order.total),
                expires_at=order.payment_voucher_expires_at,
                provider=order.payment_provider,
                barcode_url=order.payment_voucher_barcode_url,
            )
        transfer = None
        if order.payment_transfer_reference is not None:
            transfer = TransferResponse(
                clabe=order.payment_transfer_clabe,
                reference=order.payment_transfer_reference,
                amount=MoneyResponse.from_money(order.total),
                expires_at=order.payment_transfer_expires_at,
                provider=order.payment_provider,
            )
        approval = None
        if order.payment_approval_reference is not None:
            approval = ApprovalResponse(
                approval_url=order.payment_approval_url,
                reference=order.payment_approval_reference,
                amount=MoneyResponse.from_money(order.total),
                expires_at=order.payment_approval_expires_at,
                provider=order.payment_provider,
            )
        refund = None
        if order.refund_status is not None:
            refund = RefundResponse(
                refund_id=order.payment_refund_id,
                status=order.refund_status,
                amount=MoneyResponse.from_money(order.refunded_amount),
                provider=order.payment_provider,
            )
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
            voucher=voucher,
            transfer=transfer,
            approval=approval,
            refund=refund,
        )


class PaymentWebhookAck(_Camel):
    """Acknowledges a processed payment webhook (COM-206).

    Deliberately terse: it confirms receipt and echoes the referenced order's id and resulting
    status so the provider can reconcile, without leaking any other order detail to the caller.
    """

    received: bool
    order_id: uuid.UUID
    status: OrderStatus

    @classmethod
    def from_order(cls, order: Order) -> PaymentWebhookAck:
        return cls(received=True, order_id=order.id, status=order.status)


class KitchenWebhookAck(_Camel):
    """Acknowledges a processed kitchen status webhook (COM-303).

    Same terse shape as :class:`PaymentWebhookAck`: it confirms receipt and echoes the referenced
    order's id and resulting status so the kitchen can reconcile, without leaking any other detail.
    """

    received: bool
    order_id: uuid.UUID
    status: OrderStatus

    @classmethod
    def from_order(cls, order: Order) -> KitchenWebhookAck:
        return cls(received=True, order_id=order.id, status=order.status)


class SavePaymentMethodRequest(_Camel):
    """A tokenized payment method to save (COM-207).

    Carries the provider ``token`` produced by on-device tokenization — **never** a PAN or CVV —
    plus optional non-sensitive display metadata. Field *semantics* (``last4`` is four digits, the
    expiry is in range) are validated by the domain, surfacing as ``422``.
    """

    type: PaymentMethodType
    token: str
    brand: str | None = None
    last4: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None


class PaymentMethodResponse(_Camel):
    """A saved payment method projected for display (COM-207).

    Deliberately omits the stored provider ``token``: only the id and non-sensitive display
    metadata are ever returned to the client, so the reusable credential never leaves the server.
    """

    id: uuid.UUID
    type: PaymentMethodType
    brand: str | None = None
    last4: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    created_at: datetime

    @classmethod
    def from_method(cls, method: SavedPaymentMethod) -> PaymentMethodResponse:
        return cls(
            id=method.id,
            type=method.type,
            brand=method.brand,
            last4=method.last4,
            exp_month=method.exp_month,
            exp_year=method.exp_year,
            created_at=method.created_at,
        )
