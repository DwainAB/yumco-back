from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.models.user import User
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.schemas.ai_conversation import AIConversationCreate, AIConversationDetail, AIConversationSummary
from app.services.ai_conversation_service import create_ai_conversation, get_ai_conversation, list_ai_conversations
from app.services.ai_service import generate_restaurant_ai_response


router = APIRouter(prefix="/restaurants", tags=["ai"])


def _require_restaurant_owner_or_admin(restaurant_id: int, current_user: User, db: Session) -> Restaurant:
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    if current_user.is_admin:
        return restaurant

    role = db.query(Role).filter(Role.restaurant_id == restaurant_id, Role.user_id == current_user.id).first()
    if not role or role.type not in {"owner", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return restaurant


@router.post("/{restaurant_id}/ai/chat", response_model=AIChatResponse)
async def chat_with_restaurant_ai(
    restaurant_id: int,
    data: AIChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return await generate_restaurant_ai_response(db, restaurant, data)


@router.post("/{restaurant_id}/ai/conversations", response_model=AIConversationSummary, status_code=status.HTTP_201_CREATED)
def create_restaurant_ai_conversation(
    restaurant_id: int,
    data: AIConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return create_ai_conversation(db, restaurant_id, current_user.id, data.title)


@router.get("/{restaurant_id}/ai/conversations", response_model=list[AIConversationSummary])
def list_restaurant_ai_conversations(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return list_ai_conversations(db, restaurant_id)


@router.get("/{restaurant_id}/ai/conversations/{conversation_id}", response_model=AIConversationDetail)
def get_restaurant_ai_conversation(
    restaurant_id: int,
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return get_ai_conversation(db, restaurant_id, conversation_id)
