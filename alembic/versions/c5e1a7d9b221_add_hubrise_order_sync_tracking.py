"""add hubrise order sync tracking

Revision ID: c5e1a7d9b221
Revises: ab4d91e7c2f0
Create Date: 2026-04-18 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c5e1a7d9b221"
down_revision = "ab4d91e7c2f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("hubrise_order_id", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("hubrise_sync_status", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("hubrise_last_error", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("hubrise_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "hubrise_order_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("hubrise_location_id", sa.String(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_hubrise_order_logs_id"), "hubrise_order_logs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_hubrise_order_logs_id"), table_name="hubrise_order_logs")
    op.drop_table("hubrise_order_logs")

    op.drop_column("orders", "hubrise_synced_at")
    op.drop_column("orders", "hubrise_last_error")
    op.drop_column("orders", "hubrise_sync_status")
    op.drop_column("orders", "hubrise_order_id")
