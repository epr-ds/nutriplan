"""initial commerce schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-02

Creates the Commerce bounded-context tables: addresses, orders, order_items (COM-101),
with owner-scoped indexes on orders.user_id, orders.status and orders.created_at.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=False),
        sa.Column("apartment", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("zip_code", sa.String(length=16), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("instructions", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_addresses_user_id", "addresses", ["user_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("fulfillment_type", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=True),
        sa.Column(
            "delivery_address_id",
            sa.Uuid(),
            sa.ForeignKey("addresses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("delivery_time_slot", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.String(length=2048), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("delivery_fee_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="MXN"),
        sa.Column("estimated_delivery", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tracking_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("unit_price_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_addresses_user_id", table_name="addresses")
    op.drop_table("addresses")
