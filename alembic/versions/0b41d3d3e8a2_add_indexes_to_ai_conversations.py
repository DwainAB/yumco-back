"""add indexes to ai conversations

Revision ID: 0b41d3d3e8a2
Revises: a7c4e2d1f901
Create Date: 2026-04-26 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0b41d3d3e8a2"
down_revision: Union[str, Sequence[str], None] = "a7c4e2d1f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_conversations_restaurant_id_updated_at",
        "ai_conversations",
        ["restaurant_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_conversation_messages_conversation_id_created_at",
        "ai_conversation_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conversation_messages_conversation_id_created_at", table_name="ai_conversation_messages")
    op.drop_index("ix_ai_conversations_restaurant_id_updated_at", table_name="ai_conversations")
