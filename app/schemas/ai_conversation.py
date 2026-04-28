from datetime import datetime

from pydantic import BaseModel, Field


AI_CONVERSATIONS_PAGE_SIZE = 10


class AIConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AIConversationSummary(BaseModel):
    id: int
    restaurant_id: int
    created_by_user_id: int | None = None
    title: str
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class AIConversationMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIConversationDetail(AIConversationSummary):
    messages: list[AIConversationMessageResponse] = []


class AIConversationListResponse(BaseModel):
    items: list[AIConversationSummary]
    page: int
    page_size: int = AI_CONVERSATIONS_PAGE_SIZE
    total_items: int
    total_pages: int
    query: str | None = None
