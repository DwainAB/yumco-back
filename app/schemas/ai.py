from pydantic import BaseModel, Field


class AIChatMessage(BaseModel):
    role: str
    content: str


class AIChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str = Field(min_length=1, max_length=12000)
    history: list[AIChatMessage] = Field(default_factory=list, max_length=8)


class AIUsageInfo(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    remaining_messages: int
    remaining_tokens: int


class AIChatResponse(BaseModel):
    conversation_id: int
    answer: str
    model: str
    usage: AIUsageInfo


class AIWebSearchDebugInfo(BaseModel):
    forced_web_search: bool
    should_use_web_search: bool
    used_cached_web_context: bool
    selected_model: str
    tool_choice: str | None = None
    web_search_tool_attached: bool
    used_web_search_tool: bool


class AIWebSearchDebugResponse(BaseModel):
    conversation_id: int | None = None
    answer: str
    model: str
    usage: AIUsageInfo
    debug: AIWebSearchDebugInfo
