"""add allergens to products

Revision ID: f3c9d2a7b611
Revises: e1a7c4d92b31
Create Date: 2026-04-24 00:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f3c9d2a7b611"
down_revision = "e1a7c4d92b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("allergens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("products", "allergens", server_default=None)


def downgrade() -> None:
    op.drop_column("products", "allergens")
