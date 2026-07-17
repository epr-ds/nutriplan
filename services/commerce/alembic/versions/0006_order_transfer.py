"""order spei transfer

Revision ID: 0006_order_transfer
Revises: 0005_order_voucher
Create Date: 2026-07-16

Adds the SPEI bank-transfer instructions issued for an asynchronous payment to ``orders`` (COM-204):
``payment_transfer_clabe`` (the destination interbank CLABE the customer transfers to),
``payment_transfer_reference`` and ``payment_transfer_expires_at``. All nullable -- only SPEI
payments populate them, and the order stays ``pending`` until a webhook confirms the transfer landed
(COM-206).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_order_transfer"
down_revision = "0005_order_voucher"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("payment_transfer_clabe", sa.String(length=18), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("payment_transfer_reference", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column("payment_transfer_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_transfer_expires_at")
    op.drop_column("orders", "payment_transfer_reference")
    op.drop_column("orders", "payment_transfer_clabe")
