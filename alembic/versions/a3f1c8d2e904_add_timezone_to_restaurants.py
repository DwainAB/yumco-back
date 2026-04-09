"""add_timezone_to_restaurants

Revision ID: a3f1c8d2e904
Revises: 188c330a2fc6
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c8d2e904'
down_revision: Union[str, Sequence[str], None] = '188c330a2fc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('restaurants', sa.Column('timezone', sa.String(), nullable=False, server_default='Europe/Paris'))


def downgrade() -> None:
    op.drop_column('restaurants', 'timezone')