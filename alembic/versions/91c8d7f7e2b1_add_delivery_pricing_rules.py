"""add delivery pricing rules

Revision ID: 91c8d7f7e2b1
Revises: 0b41d3d3e8a2
Create Date: 2026-04-26 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "91c8d7f7e2b1"
down_revision: Union[str, Sequence[str], None] = "0b41d3d3e8a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delivery_tiers",
        sa.Column("min_order_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("items_subtotal", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("delivery_fee", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("delivery_distance_km", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.execute("UPDATE orders SET items_subtotal = amount_total, delivery_fee = 0 WHERE amount_total IS NOT NULL")


def downgrade() -> None:
    op.drop_column("orders", "delivery_distance_km")
    op.drop_column("orders", "delivery_fee")
    op.drop_column("orders", "items_subtotal")
    op.drop_column("delivery_tiers", "min_order_amount")
