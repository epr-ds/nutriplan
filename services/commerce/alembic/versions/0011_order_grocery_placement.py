"""grocery provider order placement

Revision ID: 0011_order_grocery_placement
Revises: 0010_slot_reservations
Create Date: 2026-09-05

Adds the grocery provider's own order to ``orders`` (COM-408):
``grocery_external_order_id`` (the provider's order reference, which a status poll acts on) and
``grocery_status`` (the last canonical :class:`GroceryOrderStatus` the provider reported). Both
nullable -- only a grocery order actually placed with a provider populates them. The reference is
indexed because it is the lookup key for reconciling an order from the provider's side.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_order_grocery_placement"
down_revision = "0010_slot_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("grocery_external_order_id", sa.String(length=255), nullable=True)
    )
    op.add_column("orders", sa.Column("grocery_status", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_orders_grocery_external_order_id", "orders", ["grocery_external_order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_orders_grocery_external_order_id", table_name="orders")
    op.drop_column("orders", "grocery_status")
    op.drop_column("orders", "grocery_external_order_id")
