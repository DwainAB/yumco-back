"""add kind to categories

Revision ID: ce1c2e4f9a10
Revises: b7e2a1f3c509
Create Date: 2026-04-11 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce1c2e4f9a10'
down_revision: Union[str, Sequence[str], None] = 'b7e2a1f3c509'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('kind', sa.String(), nullable=False, server_default='other'))


def downgrade() -> None:
    op.drop_column('categories', 'kind')
