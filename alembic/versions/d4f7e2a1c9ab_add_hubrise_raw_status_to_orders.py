"""add hubrise raw status to orders

Revision ID: d4f7e2a1c9ab
Revises: c5e1a7d9b221
Create Date: 2026-04-18 14:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4f7e2a1c9ab"
down_revision = "c5e1a7d9b221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("hubrise_raw_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "hubrise_raw_status")
