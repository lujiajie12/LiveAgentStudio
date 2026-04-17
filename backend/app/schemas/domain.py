from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    broadcaster = "broadcaster"
    operator = "operator"
    admin = "admin"


class SessionStatus(str, Enum):
    active = "active"
    ended = "ended"
    archived = "archived"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class LiveStage(str, Enum):
    warmup = "warmup"
    intro = "intro"
    pitch = "pitch"
    closing = "closing"


class IntentType(str, Enum):
    direct = "direct"
    qa = "qa"
    script = "script"
    analyst = "analyst"
    unknown = "unknown"


class UserRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    username: str
    role: UserRole
    tenant_id: str | None = None
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    live_room_id: str | None = None
    current_product_id: str | None = None
    live_stage: LiveStage = LiveStage.warmup
    status: SessionStatus = SessionStatus.active
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MessageRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    role: MessageRole
    content: str
    intent: IntentType | None = None
    agent_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeDocumentRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    source_type: str
    product_id: str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCallLogRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    trace_id: str | None = None
    tool_name: str
    node_name: str | None = None
    category: str = "misc"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_summary: str | None = None
    latency_ms: int = 0
    status: str = "ok"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReportRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    summary: str
    total_messages: int = 0
    intent_distribution: dict[str, float] = Field(default_factory=dict)
    top_questions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    hot_products: list[str] = Field(default_factory=list)
    script_usage: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HighFrequencyQuestionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str
    question: str
    normalized_question: str
    frequency: int = 1
    source_session_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentPreferenceRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    script_style: str | None = None
    custom_sensitive_terms: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LiveBarrageEventRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    user_id: str | None = None
    display_name: str
    text: str
    source: str = "simulator"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TeleprompterItemRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    title: str
    content: str
    source_agent: str = "qa"
    priority: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RagOfflineJobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    job_type: str
    status: str = "queued"
    docs_dir: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    log_path: str | None = None
    pid: int | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
