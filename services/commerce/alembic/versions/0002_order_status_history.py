"""order status history

Revision ID: 0002_order_status_history
Revises: 0001_initial
Create Date: 2026-07-06

Adds the ``order_status_history`` table (COM-106): one row per lifecycle transition of an order,
with ``order_id`` indexed for the aggregate's history fan-out and cascade-deleted with its order.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_order_status_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_order_status_history_order_id", "order_status_history", ["order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")
