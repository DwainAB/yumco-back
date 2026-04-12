"""add pending online orders

Revision ID: 6f4a2c8d1e77
Revises: 9f1c3a2b4d55
Create Date: 2026-04-12 12:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6f4a2c8d1e77"
down_revision = "9f1c3a2b4d55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_online_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("checkout_session_id", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkout_session_id"),
    )
    op.create_index(op.f("ix_pending_online_orders_id"), "pending_online_orders", ["id"], unique=False)
    op.create_index(op.f("ix_pending_online_orders_checkout_session_id"), "pending_online_orders", ["checkout_session_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_pending_online_orders_checkout_session_id"), table_name="pending_online_orders")
    op.drop_index(op.f("ix_pending_online_orders_id"), table_name="pending_online_orders")
    op.drop_table("pending_online_orders")
