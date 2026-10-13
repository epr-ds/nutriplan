"""dark-kitchen delivery slot reservations

Revision ID: 0010_slot_reservations
Revises: 0009_order_refund
Create Date: 2026-08-12

Adds the ``slot_reservations`` table (COM-304): one row per order holds a dark-kitchen delivery
window, consuming one unit of that window's daily capacity for a service zone (the delivery
postcode). ``order_id`` is unique (an order holds at most one reservation) and there is no foreign
key to ``orders`` so the reservation can be inserted in the same transaction before the order row.
``(service_zone, delivery_date, delivery_time_slot)`` is indexed for the capacity count that the
reservation guard and availability (COM-302) both read.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_slot_reservations"
down_revision = "0009_order_refund"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slot_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("service_zone", sa.String(length=16), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("delivery_time_slot", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_slot_reservations_order"),
    )
    op.create_index(
        "ix_slot_reservations_zone_date_slot",
        "slot_reservations",
        ["service_zone", "delivery_date", "delivery_time_slot"],
    )


def downgrade() -> None:
    op.drop_index("ix_slot_reservations_zone_date_slot", table_name="slot_reservations")
    op.drop_table("slot_reservations")
