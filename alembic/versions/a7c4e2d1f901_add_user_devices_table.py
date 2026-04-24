"""add user devices table

Revision ID: a7c4e2d1f901
Revises: f3c9d2a7b611
Create Date: 2026-04-24 02:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7c4e2d1f901"
down_revision = "f3c9d2a7b611"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expo_push_token", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("device_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("expo_push_token", name="uq_user_devices_expo_push_token"),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])
    op.create_index("ix_user_devices_expo_push_token", "user_devices", ["expo_push_token"], unique=True)

    op.execute(
        """
        INSERT INTO user_devices (user_id, expo_push_token, is_active, created_at, updated_at, last_seen_at)
        SELECT id, expo_push_token, TRUE, NOW(), NOW(), NOW()
        FROM users
        WHERE expo_push_token IS NOT NULL AND expo_push_token <> ''
        """
    )

    op.alter_column("user_devices", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_user_devices_expo_push_token", table_name="user_devices")
    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")
