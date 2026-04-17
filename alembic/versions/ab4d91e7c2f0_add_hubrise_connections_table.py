"""add hubrise connections table

Revision ID: ab4d91e7c2f0
Revises: f2b8d6a1c333
Create Date: 2026-04-17 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "ab4d91e7c2f0"
down_revision = "f2b8d6a1c333"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hubrise_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("hubrise_location_id", sa.String(), nullable=False),
        sa.Column("hubrise_account_id", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("token_type", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id"),
    )
    op.create_index(op.f("ix_hubrise_connections_id"), "hubrise_connections", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_hubrise_connections_id"), table_name="hubrise_connections")
    op.drop_table("hubrise_connections")
