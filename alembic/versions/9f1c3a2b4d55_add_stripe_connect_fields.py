"""add stripe connect fields

Revision ID: 9f1c3a2b4d55
Revises: f1b3b4b927aa
Create Date: 2026-04-11 20:12:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f1c3a2b4d55"
down_revision = "f1b3b4b927aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("stripe_charges_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("restaurants", sa.Column("stripe_payouts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("restaurants", sa.Column("stripe_details_submitted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("orders", sa.Column("stripe_checkout_session_id", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("stripe_payment_intent_id", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("stripe_charge_id", sa.String(), nullable=True))
    op.alter_column("restaurants", "stripe_charges_enabled", server_default=None)
    op.alter_column("restaurants", "stripe_payouts_enabled", server_default=None)
    op.alter_column("restaurants", "stripe_details_submitted", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "stripe_charge_id")
    op.drop_column("orders", "stripe_payment_intent_id")
    op.drop_column("orders", "stripe_checkout_session_id")
    op.drop_column("restaurants", "stripe_details_submitted")
    op.drop_column("restaurants", "stripe_payouts_enabled")
    op.drop_column("restaurants", "stripe_charges_enabled")
