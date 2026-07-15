"""SQLAlchemy ORM models for the Commerce bounded context (COM-101, COM-106, COM-202).

Four tables — ``addresses``, ``orders``, ``order_items`` and ``order_status_history`` — persist the
``Order`` aggregate. Owner-scoped query paths are indexed per the acceptance criteria:
``orders.user_id``, ``orders.status`` and ``orders.created_at`` (for "my recent orders" listings),
``order_items.order_id`` for the aggregate's item fan-out, and ``order_status_history.order_id`` for
its transition history (COM-106). ``orders`` also records the card-charge outcome (COM-202:
``payment_status``/``payment_provider``/``payment_charge_id``) — a reference only, never a PAN. The
``idempotency_keys`` table (COM-209) de-duplicates create-order retries, unique per
``(user_id, idempotency_key)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
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
