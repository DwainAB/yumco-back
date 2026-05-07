"""add printer fields to restaurant config

Revision ID: b4c2d9e7f301
Revises: a7c4e2d1f901
Create Date: 2026-05-07 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b4c2d9e7f301"
down_revision = "a7c4e2d1f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_configs",
        sa.Column("printer_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("restaurant_configs", sa.Column("printer_name", sa.String(), nullable=True))
    op.add_column("restaurant_configs", sa.Column("printer_host", sa.String(), nullable=True))
    op.add_column("restaurant_configs", sa.Column("printer_port", sa.Integer(), nullable=True))
    op.add_column("restaurant_configs", sa.Column("printer_paper_width", sa.Integer(), nullable=True))
    op.alter_column("restaurant_configs", "printer_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("restaurant_configs", "printer_paper_width")
    op.drop_column("restaurant_configs", "printer_port")
    op.drop_column("restaurant_configs", "printer_host")
    op.drop_column("restaurant_configs", "printer_name")
    op.drop_column("restaurant_configs", "printer_enabled")
