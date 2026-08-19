"""SQLAlchemy ORM models for the Commerce bounded context (COM-101, COM-106, COM-202).

Four tables — ``addresses``, ``orders``, ``order_items`` and ``order_status_history`` — persist the
``Order`` aggregate. Owner-scoped query paths are indexed per the acceptance criteria:
``orders.user_id``, ``orders.status`` and ``orders.created_at`` (for "my recent orders" listings),
``order_items.order_id`` for the aggregate's item fan-out, and ``order_status_history.order_id`` for
its transition history (COM-106). ``orders`` also records the card-charge outcome (COM-202:
``payment_status``/``payment_provider``/``payment_charge_id``) — a reference only, never a PAN — and
the OXXO voucher issued for an async payment (COM-203:
``payment_voucher_reference``/``…_expires_at``/``…_barcode_url``) and the SPEI bank-transfer
instructions issued for an async payment (COM-204:
``payment_transfer_clabe``/``…_reference``/``…_expires_at``) and the PayPal redirect-approval order
``payment_approval_reference``/``…_url``/``…_expires_at``) and the refund captured when a paid order
is cancelled (COM-208: ``payment_refund_id``/``refund_status``/``refunded_amount``). The
``idempotency_keys`` table (COM-209) de-duplicates create-order retries, unique per
``(user_id, idempotency_key)``, and the ``payment_methods`` table (COM-207) stores a user's
tokenized payment instruments — a provider token plus non-sensitive display metadata, never a PAN.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AddressModel(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    apartment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(16), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    instructions: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    fulfillment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_address_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("addresses.id", ondelete="RESTRICT"), nullable=False
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_time_slot: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    delivery_fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MXN")
    estimated_delivery: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tracking_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Payment outcome captured when a card is charged inline at checkout (COM-202); all nullable
    # because cash / async methods leave the order unpaid until a later webhook confirms it.
    payment_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Offline voucher issued for an async method (OXXO, COM-203): the reference the customer pays
    # against, its expiry, and an optional barcode. Nullable -- only set for voucher payments.
    payment_voucher_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_voucher_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_voucher_barcode_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Bank-transfer instructions issued for an async method (SPEI, COM-204): the destination CLABE
    # and reference the customer transfers to, and when they expire. Nullable -- only SPEI uses it.
    payment_transfer_clabe: Mapped[str | None] = mapped_column(String(18), nullable=True)
    payment_transfer_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_transfer_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Redirect-approval order created for an async method (PayPal, COM-205): the provider's order
    # reference, the URL the customer approves at, and when it expires. Nullable -- only PayPal
    # populates them.
    payment_approval_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_approval_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    payment_approval_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Refund captured when a paid order is cancelled (COM-208): the provider's refund reference,
    # whether the whole total or only part was returned (``full``/``partial``), and the exact amount
    # refunded. Nullable -- only a paid, cancelled order that was actually refunded populates them.
    payment_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refund_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    refunded_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    delivery_address: Mapped[AddressModel] = relationship(lazy="selectin")
    items: Mapped[list[OrderItemModel]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItemModel.position",
        lazy="selectin",
    )
    status_history: Mapped[list[OrderStatusHistoryModel]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistoryModel.position",
        lazy="selectin",
    )


class OrderStatusHistoryModel(Base):
    """One row per lifecycle transition of an order (COM-106).

    ``position`` preserves chronological order independently of clock skew, and ``order_id`` is
    indexed for the aggregate's history fan-out.
    """

    __tablename__ = "order_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped[OrderModel] = relationship(back_populates="status_history")


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[OrderModel] = relationship(back_populates="items")


class IdempotencyKeyModel(Base):
    """A client ``Idempotency-Key`` and the order that a create-order request produced (COM-209).

    Unique per ``(user_id, idempotency_key)`` so the same key can be reused freely by different
    users; ``request_fingerprint`` is a hash of the originating request, compared on replay to
    reject the same key presented with a different body. Only successful creates are recorded, so a
    declined or invalid request leaves no key behind and can be retried.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_keys_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class PaymentMethodModel(Base):
    """A user's saved, tokenized payment method (COM-207).

    Persists only the provider ``token`` (never a PAN or CVV) plus non-sensitive display metadata
    (``brand``/``last4``/expiry) so the app can show "Visa ****4242" at checkout. The token is a
    stored credential and is deliberately never projected back onto the API. ``user_id`` is indexed
    for the per-user list; a user may save several methods, so there is no uniqueness constraint.
    """

    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SlotReservationModel(Base):
    """One dark-kitchen delivery-window booking held for an order (COM-304).

    A reservation consumes one unit of a delivery window's daily capacity for a service zone
    (identified by the delivery postcode). ``order_id`` is unique so an order holds at most one
    reservation, and there is deliberately **no** foreign key to ``orders`` so the reservation can
    be inserted in the same transaction *before* the order row (the capacity guard must run first).
    ``(service_zone, delivery_date, delivery_time_slot)`` is indexed for the capacity count that
    availability (COM-302) and the reservation guard both read. Released (row deleted) when the
    order is cancelled.
    """

    __tablename__ = "slot_reservations"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_slot_reservations_order"),
        Index(
            "ix_slot_reservations_zone_date_slot",
            "service_zone",
            "delivery_date",
            "delivery_time_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    service_zone: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_time_slot: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
