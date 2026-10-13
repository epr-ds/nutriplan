"""order payment reference

Revision ID: 0003_order_payment
Revises: 0002_order_status_history
Create Date: 2026-07-13

Adds the card-charge outcome to ``orders`` (COM-202): ``payment_status``, ``payment_provider`` and
``payment_charge_id``. All nullable -- cash and asynchronous methods (OXXO/SPEI) leave an order
unpaid until a later webhook confirms it. ``payment_charge_id`` is the provider's charge reference a
refund (COM-208) acts on; we store this opaque handle only, never a PAN.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_order_payment"
down_revision = "0002_order_status_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_status", sa.String(length=16), nullable=True))
    op.add_column("orders", sa.Column("payment_provider", sa.String(length=32), nullable=True))
    op.add_column("orders", sa.Column("payment_charge_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_charge_id")
    op.drop_column("orders", "payment_provider")
    op.drop_column("orders", "payment_status")
