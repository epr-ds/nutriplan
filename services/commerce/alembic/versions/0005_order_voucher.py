"""order oxxo voucher

Revision ID: 0005_order_voucher
Revises: 0004_idempotency_keys
Create Date: 2026-07-15

Adds the OXXO voucher issued for an asynchronous payment to ``orders`` (COM-203):
``payment_voucher_reference`` (the reference the customer pays against), ``payment_voucher_expires_at``
and ``payment_voucher_barcode_url``. All nullable -- only voucher payments populate them, and the
order stays ``pending`` until a webhook confirms the cash payment settled (COM-206).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_order_voucher"
down_revision = "0004_idempotency_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("payment_voucher_reference", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("payment_voucher_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("payment_voucher_barcode_url", sa.String(length=2048), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_voucher_barcode_url")
    op.drop_column("orders", "payment_voucher_expires_at")
    op.drop_column("orders", "payment_voucher_reference")
