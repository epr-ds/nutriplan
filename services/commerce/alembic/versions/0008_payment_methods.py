"""payment methods

Revision ID: 0008_payment_methods
Revises: 0007_order_approval
Create Date: 2026-08-05

Adds the ``payment_methods`` table (COM-207) so a user can save tokenized payment instruments for
reuse at checkout. Each row stores the provider ``token`` (never a PAN/CVV) alongside non-sensitive
display metadata (``brand``/``last4``/``exp_month``/``exp_year``); ``user_id`` is indexed for the
per-user list. A user may save several methods, so there is no uniqueness constraint.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_payment_methods"
down_revision = "0007_order_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("brand", sa.String(length=40), nullable=True),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("exp_month", sa.Integer(), nullable=True),
        sa.Column("exp_year", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")
