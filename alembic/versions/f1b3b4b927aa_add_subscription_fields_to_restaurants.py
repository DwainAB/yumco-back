"""add subscription fields to restaurants

Revision ID: f1b3b4b927aa
Revises: ce1c2e4f9a10
Create Date: 2026-04-11 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b3b4b927aa'
down_revision: Union[str, Sequence[str], None] = 'ce1c2e4f9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('restaurants', sa.Column('subscription_plan', sa.String(), nullable=False, server_default='starter'))
    op.add_column('restaurants', sa.Column('ai_monthly_quota', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('restaurants', sa.Column('ai_usage_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('restaurants', sa.Column('ai_monthly_token_quota', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('restaurants', sa.Column('ai_token_usage_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('restaurants', sa.Column('ai_cycle_started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('restaurants', 'ai_cycle_started_at')
    op.drop_column('restaurants', 'ai_token_usage_count')
    op.drop_column('restaurants', 'ai_monthly_token_quota')
    op.drop_column('restaurants', 'ai_usage_count')
    op.drop_column('restaurants', 'ai_monthly_quota')
    op.drop_column('restaurants', 'subscription_plan')
