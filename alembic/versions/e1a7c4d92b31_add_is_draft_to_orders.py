"""add is_draft to orders

Revision ID: e1a7c4d92b31
Revises: d4f7e2a1c9ab
Create Date: 2026-04-18 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e1a7c4d92b31"
down_revision = "d4f7e2a1c9ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("orders", "is_draft", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "is_draft")
