"""add review followups and google review url

Revision ID: 7f2e6c1d4a90
Revises: c3d8e2a7f114
Create Date: 2026-05-12 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7f2e6c1d4a90"
down_revision = "c3d8e2a7f114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("google_review_url", sa.String(), nullable=True))

    op.create_table(
        "review_followups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(), nullable=False),
        sa.Column("customer_first_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index(op.f("ix_review_followups_id"), "review_followups", ["id"], unique=False)
    op.create_index(op.f("ix_review_followups_order_id"), "review_followups", ["order_id"], unique=False)
    op.create_index(op.f("ix_review_followups_restaurant_id"), "review_followups", ["restaurant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_followups_restaurant_id"), table_name="review_followups")
    op.drop_index(op.f("ix_review_followups_order_id"), table_name="review_followups")
    op.drop_index(op.f("ix_review_followups_id"), table_name="review_followups")
    op.drop_table("review_followups")
    op.drop_column("restaurants", "google_review_url")
