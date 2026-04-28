from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_conversation import AIConversation
from app.models.ai_conversation_message import AIConversationMessage


def create_ai_conversation(db: Session, restaurant_id: int, user_id: int, title: str) -> AIConversation:
    conversation = AIConversation(
        restaurant_id=restaurant_id,
        created_by_user_id=user_id,
        title=title.strip(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_ai_conversations(
    db: Session,
    restaurant_id: int,
    page: int,
    query: str | None = None,
    page_size: int = 10,
) -> tuple[list[AIConversation], int]:
    conversations_query = db.query(AIConversation).filter(AIConversation.restaurant_id == restaurant_id)

    normalized_query = query.strip() if query else None
    if normalized_query:
        conversations_query = conversations_query.filter(
            func.lower(AIConversation.title).contains(normalized_query.lower())
        )

    total_items = conversations_query.count()
    items = (
        conversations_query
        .order_by(AIConversation.updated_at.desc(), AIConversation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total_items


def get_ai_conversation(db: Session, restaurant_id: int, conversation_id: int) -> AIConversation:
    conversation = (
        db.query(AIConversation)
        .filter(AIConversation.restaurant_id == restaurant_id, AIConversation.id == conversation_id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def add_ai_conversation_message(
    db: Session,
    conversation: AIConversation,
    role: str,
    content: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> AIConversationMessage:
    message = AIConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
    db.add(message)
    db.flush()
    conversation.updated_at = message.created_at
    db.commit()
    db.refresh(message)
    db.refresh(conversation)
    return message
