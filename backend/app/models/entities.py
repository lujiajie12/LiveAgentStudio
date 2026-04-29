from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> str:
    return str(uuid4())


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    live_room_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    live_stage: Mapped[str] = mapped_column(String(32), default="warmup")
    status: Mapped[str] = mapped_column(String(32), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class MessageORM(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeDocumentORM(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(64))
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ToolCallLogORM(Base):
    __tablename__ = "tool_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    node_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), default="misc", index=True)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ReportORM(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    summary: Mapped[str] = mapped_column(Text)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    intent_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    top_questions: Mapped[list] = mapped_column(JSON, default=list)
    unresolved_questions: Mapped[list] = mapped_column(JSON, default=list)
    hot_products: Mapped[list] = mapped_column(JSON, default=list)
    script_usage: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HighFrequencyQuestionORM(Base):
    __tablename__ = "high_frequency_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    normalized_question: Mapped[str] = mapped_column(String(512), index=True)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    source_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class AgentPreferenceORM(Base):
    __tablename__ = "agent_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    script_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_sensitive_terms: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class LiveBarrageEventORM(Base):
    __tablename__ = "live_barrage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="simulator", index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TeleprompterItemORM(Base):
    __tablename__ = "teleprompter_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source_agent: Mapped[str] = mapped_column(String(64), default="qa", index=True)
    priority: Mapped[str] = mapped_column(String(32), default="normal", index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        index=True,
    )


class RagOfflineJobORM(Base):
    __tablename__ = "rag_offline_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    docs_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
