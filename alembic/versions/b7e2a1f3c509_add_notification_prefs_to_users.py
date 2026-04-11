"""add_notification_prefs_to_users

Revision ID: b7e2a1f3c509
Revises: a3f1c8d2e904
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2a1f3c509'
down_revision: Union[str, Sequence[str], None] = 'a3f1c8d2e904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('notify_orders', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('notify_reservations', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('users', 'notify_reservations')
    op.drop_column('users', 'notify_orders')
