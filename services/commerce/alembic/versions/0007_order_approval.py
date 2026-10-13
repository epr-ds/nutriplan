"""order paypal approval

Revision ID: 0007_order_approval
Revises: 0006_order_transfer
Create Date: 2026-08-01

Adds the PayPal redirect-approval order created for an asynchronous payment to ``orders`` (COM-205):
``payment_approval_reference`` (the provider's order id a later capture/refund acts on),
``payment_approval_url`` (the URL the customer is redirected to approve the payment) and
``payment_approval_expires_at``. All nullable -- only PayPal payments populate them, and the order
stays ``pending`` until a webhook confirms the captured payment (COM-206).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_order_approval"
down_revision = "0006_order_transfer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("payment_approval_reference", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("payment_approval_url", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column("payment_approval_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_approval_expires_at")
    op.drop_column("orders", "payment_approval_url")
    op.drop_column("orders", "payment_approval_reference")
