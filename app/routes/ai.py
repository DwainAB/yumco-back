from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.models.user import User
from app.schemas.ai import AIChatRequest, AIChatResponse, AIWebSearchDebugResponse
from app.schemas.ai_conversation import (
    AI_CONVERSATIONS_PAGE_SIZE,
    AIConversationCreate,
    AIConversationDetail,
    AIConversationListResponse,
    AIConversationSummary,
)
from app.services.ai_conversation_service import create_ai_conversation, get_ai_conversation, list_ai_conversations
from app.services.ai_service import (
    debug_restaurant_ai_web_search as generate_restaurant_ai_response_debug,
    generate_restaurant_ai_response,
)


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


@router.post("/{restaurant_id}/ai/debug/web-search", response_model=AIWebSearchDebugResponse)
async def debug_restaurant_ai_web_search_route(
    restaurant_id: int,
    data: AIChatRequest,
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    result = await generate_restaurant_ai_response_debug(db, restaurant, data)
    if isinstance(result, tuple) and len(result) == 2:
        response, debug = result
    else:
        response = result
        debug = {
            "forced_web_search": True,
            "should_use_web_search": True,
            "used_cached_web_context": False,
            "selected_model": getattr(response, "model", None) or (response.get("model") if isinstance(response, dict) else None) or "unknown",
            "tool_choice": "required",
            "web_search_tool_attached": True,
            "used_web_search_tool": False,
        }
    return AIWebSearchDebugResponse(
        conversation_id=data.conversation_id,
        answer=response.answer if hasattr(response, "answer") else response["answer"],
        model=response.model if hasattr(response, "model") else response["model"],
        usage=response.usage if hasattr(response, "usage") else response["usage"],
        debug=debug,
    )


@router.post("/{restaurant_id}/ai/conversations", response_model=AIConversationSummary, status_code=status.HTTP_201_CREATED)
def create_restaurant_ai_conversation(
    restaurant_id: int,
    data: AIConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return create_ai_conversation(db, restaurant_id, current_user.id, data.title)


@router.get("/{restaurant_id}/ai/conversations", response_model=AIConversationListResponse)
def list_restaurant_ai_conversations(
    restaurant_id: int,
    page: int = Query(default=1, ge=1),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    items, total_items = list_ai_conversations(
        db,
        restaurant_id,
        page=page,
        query=q,
        page_size=AI_CONVERSATIONS_PAGE_SIZE,
    )
    total_pages = max(1, (total_items + AI_CONVERSATIONS_PAGE_SIZE - 1) // AI_CONVERSATIONS_PAGE_SIZE)
    return AIConversationListResponse(
        items=items,
        page=page,
        page_size=AI_CONVERSATIONS_PAGE_SIZE,
        total_items=total_items,
        total_pages=total_pages,
        query=q.strip() if q else None,
    )


@router.get("/{restaurant_id}/ai/conversations/{conversation_id}", response_model=AIConversationDetail)
def get_restaurant_ai_conversation(
    restaurant_id: int,
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return get_ai_conversation(db, restaurant_id, conversation_id)
