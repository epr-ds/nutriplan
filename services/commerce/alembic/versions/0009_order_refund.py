"""order refund on cancellation

Revision ID: 0009_order_refund
Revises: 0008_payment_methods
Create Date: 2026-08-05

Adds the refund captured when a paid order is cancelled to ``orders`` (COM-208):
``payment_refund_id`` (the provider's refund reference), ``refund_status`` (``full`` or ``partial``)
and ``refunded_amount`` (the exact amount returned). All nullable -- only a paid, cancelled order
that was actually refunded populates them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_order_refund"
down_revision = "0008_payment_methods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("payment_refund_id", sa.String(length=255), nullable=True)
    )
    op.add_column("orders", sa.Column("refund_status", sa.String(length=16), nullable=True))
    op.add_column(
        "orders", sa.Column("refunded_amount", sa.Numeric(precision=12, scale=2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "refunded_amount")
    op.drop_column("orders", "refund_status")
    op.drop_column("orders", "payment_refund_id")
