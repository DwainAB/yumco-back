"""add restaurant announcements

Revision ID: c3d8e2a7f114
Revises: 1a6e4d9c7b02
Create Date: 2026-05-08 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d8e2a7f114"
down_revision = "1a6e4d9c7b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "restaurant_announcements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("display_scope", sa.String(), nullable=False, server_default="all"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_restaurant_announcements_id"), "restaurant_announcements", ["id"], unique=False)
    op.create_index(op.f("ix_restaurant_announcements_restaurant_id"), "restaurant_announcements", ["restaurant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_restaurant_announcements_restaurant_id"), table_name="restaurant_announcements")
    op.drop_index(op.f("ix_restaurant_announcements_id"), table_name="restaurant_announcements")
    op.drop_table("restaurant_announcements")
