"""add stripe billing fields to restaurants

Revision ID: c1f42c3e9a01
Revises: 9f1c3a2b4d55
Create Date: 2026-04-12 21:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c1f42c3e9a01"
down_revision = "9f1c3a2b4d55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("subscription_interval", sa.String(), nullable=False, server_default="month"))
    op.add_column("restaurants", sa.Column("subscription_status", sa.String(), nullable=True))
    op.add_column("restaurants", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("restaurants", sa.Column("stripe_subscription_id", sa.String(), nullable=True))
    op.add_column("restaurants", sa.Column("has_tablet_rental", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("restaurants", sa.Column("has_printer_rental", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("restaurants", "subscription_interval", server_default=None)
    op.alter_column("restaurants", "has_tablet_rental", server_default=None)
    op.alter_column("restaurants", "has_printer_rental", server_default=None)


def downgrade() -> None:
    op.drop_column("restaurants", "has_printer_rental")
    op.drop_column("restaurants", "has_tablet_rental")
    op.drop_column("restaurants", "stripe_subscription_id")
    op.drop_column("restaurants", "stripe_customer_id")
    op.drop_column("restaurants", "subscription_status")
    op.drop_column("restaurants", "subscription_interval")
