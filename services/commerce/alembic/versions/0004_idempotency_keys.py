"""idempotency keys

Revision ID: 0004_idempotency_keys
Revises: 0003_order_payment
Create Date: 2026-07-14

Adds the ``idempotency_keys`` table (COM-209) so a client ``Idempotency-Key`` de-duplicates
create-order retries: it maps ``(user_id, idempotency_key)`` to the ``order_id`` that request
produced, alongside a ``request_fingerprint`` used to reject the same key reused for a different
body. Unique on ``(user_id, idempotency_key)``; ``user_id`` is indexed for the per-user lookup.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_idempotency_keys"
down_revision = "0003_order_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_keys_user_key"),
    )
    op.create_index(
        "ix_idempotency_keys_user_id", "idempotency_keys", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_user_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
