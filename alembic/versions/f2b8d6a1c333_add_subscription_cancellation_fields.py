"""add subscription cancellation fields

Revision ID: f2b8d6a1c333
Revises: e4a7b9c2d111
Create Date: 2026-04-12 23:18:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f2b8d6a1c333"
down_revision = "e4a7b9c2d111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("subscription_cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("restaurants", sa.Column("subscription_current_period_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("restaurants", "subscription_cancel_at_period_end", server_default=None)


def downgrade() -> None:
    op.drop_column("restaurants", "subscription_current_period_ends_at")
    op.drop_column("restaurants", "subscription_cancel_at_period_end")
