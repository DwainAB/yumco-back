"""add restaurant promo codes and order discount fields

Revision ID: 5b1f7d2e9c01
Revises: e4a7b9c2d111
Create Date: 2026-05-08 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5b1f7d2e9c01"
down_revision = "b4c2d9e7f301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "restaurant_promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("discount_type", sa.String(), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_restaurant_promo_codes_code"), "restaurant_promo_codes", ["code"], unique=False)
    op.create_index(op.f("ix_restaurant_promo_codes_id"), "restaurant_promo_codes", ["id"], unique=False)
    op.create_index(op.f("ix_restaurant_promo_codes_restaurant_id"), "restaurant_promo_codes", ["restaurant_id"], unique=False)

    op.add_column("orders", sa.Column("promo_code", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("discount_type", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("discount_value", sa.Numeric(10, 2), nullable=True))
    op.add_column("orders", sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))
    op.add_column("orders", sa.Column("amount_before_discount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))

    op.execute("UPDATE orders SET discount_amount = 0.00 WHERE discount_amount IS NULL")
    op.execute("UPDATE orders SET amount_before_discount = amount_total WHERE amount_before_discount IS NULL")

    op.alter_column("orders", "discount_amount", server_default=None)
    op.alter_column("orders", "amount_before_discount", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "amount_before_discount")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "discount_value")
    op.drop_column("orders", "discount_type")
    op.drop_column("orders", "promo_code")

    op.drop_index(op.f("ix_restaurant_promo_codes_restaurant_id"), table_name="restaurant_promo_codes")
    op.drop_index(op.f("ix_restaurant_promo_codes_id"), table_name="restaurant_promo_codes")
    op.drop_index(op.f("ix_restaurant_promo_codes_code"), table_name="restaurant_promo_codes")
    op.drop_table("restaurant_promo_codes")
