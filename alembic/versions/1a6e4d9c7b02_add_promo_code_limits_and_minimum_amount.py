"""add promo code limits and minimum amount

Revision ID: 1a6e4d9c7b02
Revises: 5b1f7d2e9c01
Create Date: 2026-05-08 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1a6e4d9c7b02"
down_revision = "5b1f7d2e9c01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurant_promo_codes", sa.Column("minimum_order_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("restaurant_promo_codes", sa.Column("usage_limit", sa.Integer(), nullable=True))
    op.add_column("restaurant_promo_codes", sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE restaurant_promo_codes SET usage_count = 0 WHERE usage_count IS NULL")
    op.alter_column("restaurant_promo_codes", "usage_count", server_default=None)


def downgrade() -> None:
    op.drop_column("restaurant_promo_codes", "usage_count")
    op.drop_column("restaurant_promo_codes", "usage_limit")
    op.drop_column("restaurant_promo_codes", "minimum_order_amount")
