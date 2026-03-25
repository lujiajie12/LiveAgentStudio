from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.domain import IntentType, LiveStage, MessageRole


class ChatStreamRequest(BaseModel):
    session_id: str
    user_input: str = Field(min_length=1, max_length=2000)
    current_product_id: str | None = None
    live_stage: LiveStage = LiveStage.warmup
    hot_keywords: list[str] = Field(default_factory=list)
    script_style: str | None = None
    live_offer_snapshot: dict[str, Any] = Field(default_factory=dict)


class ChatEvent(BaseModel):
    event: str
    data: dict[str, Any]


class SessionMessage(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    intent: IntentType | None = None
    agent_name: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
