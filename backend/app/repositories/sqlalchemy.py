from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import (
    AgentPreferenceORM,
    HighFrequencyQuestionORM,
    KnowledgeDocumentORM,
    LiveBarrageEventORM,
    MessageORM,
    RagOfflineJobORM,
    ReportORM,
    SessionORM,
    TeleprompterItemORM,
    ToolCallLogORM,
    UserORM,
)
from app.repositories.base import (
    AgentPreferenceRepository,
    HighFrequencyQuestionRepository,
    KnowledgeRepository,
    LiveBarrageEventRepository,
    MessageRepository,
    RagOfflineJobRepository,
    ReportRepository,
    SessionRepository,
    TeleprompterItemRepository,
    ToolCallLogRepository,
    UserRepository,
)
from app.schemas.domain import (
    AgentPreferenceRecord,
    HighFrequencyQuestionRecord,
    KnowledgeDocumentRecord,
    LiveBarrageEventRecord,
    MessageRecord,
    RagOfflineJobRecord,
    ReportRecord,
    SessionRecord,
    TeleprompterItemRecord,
    ToolCallLogRecord,
    UserRecord,
)

SessionFactory = Callable[[], Session]


def _user_record(item: UserORM) -> UserRecord:
    return UserRecord(
        id=item.id,
        username=item.username,
        role=item.role,
        tenant_id=item.tenant_id,
        password_hash=item.password_hash,
        created_at=item.created_at,
    )


def _session_record(item: SessionORM) -> SessionRecord:
    return SessionRecord(
        id=item.id,
        user_id=item.user_id,
        live_room_id=item.live_room_id,
        current_product_id=item.current_product_id,
        live_stage=item.live_stage,
        status=item.status,
        started_at=item.started_at,
        updated_at=item.updated_at,
    )


def _message_record(item: MessageORM) -> MessageRecord:
    return MessageRecord(
        id=item.id,
        session_id=item.session_id,
        role=item.role,
        content=item.content,
        intent=item.intent,
        agent_name=item.agent_name,
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


def _knowledge_record(item: KnowledgeDocumentORM) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=item.id,
        title=item.title,
        source_type=item.source_type,
        product_id=item.product_id,
        content=item.content,
        metadata=item.metadata_json or {},
        version=item.version,
        is_active=item.is_active,
        created_at=item.created_at,
    )


def _tool_log_record(item: ToolCallLogORM) -> ToolCallLogRecord:
    return ToolCallLogRecord(
        id=item.id,
        session_id=item.session_id,
        trace_id=item.trace_id,
        tool_name=item.tool_name,
        node_name=item.node_name,
        category=item.category,
        input_payload=item.input_payload or {},
        output_summary=item.output_summary,
        latency_ms=item.latency_ms,
        status=item.status,
        created_at=item.created_at,
    )


def _report_record(item: ReportORM) -> ReportRecord:
    return ReportRecord(
        id=item.id,
        session_id=item.session_id,
        summary=item.summary,
        total_messages=item.total_messages,
        intent_distribution=item.intent_distribution or {},
        top_questions=item.top_questions or [],
        unresolved_questions=item.unresolved_questions or [],
        hot_products=item.hot_products or [],
        script_usage=item.script_usage or [],
        suggestions=item.suggestions or [],
        created_at=item.created_at,
    )


def _hfq_record(item: HighFrequencyQuestionORM) -> HighFrequencyQuestionRecord:
    return HighFrequencyQuestionRecord(
        id=item.id,
        product_id=item.product_id,
        question=item.question,
        normalized_question=item.normalized_question,
        frequency=item.frequency,
        source_session_id=item.source_session_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _preference_record(item: AgentPreferenceORM) -> AgentPreferenceRecord:
    return AgentPreferenceRecord(
        id=item.id,
        user_id=item.user_id,
        script_style=item.script_style,
        custom_sensitive_terms=item.custom_sensitive_terms or [],
        metadata=item.metadata_json or {},
        updated_at=item.updated_at,
    )


def _live_barrage_record(item: LiveBarrageEventORM) -> LiveBarrageEventRecord:
    return LiveBarrageEventRecord(
        id=item.id,
        session_id=item.session_id,
        user_id=item.user_id,
        display_name=item.display_name,
        text=item.text,
        source=item.source,
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


def _teleprompter_record(item: TeleprompterItemORM) -> TeleprompterItemRecord:
    return TeleprompterItemRecord(
        id=item.id,
        session_id=item.session_id,
        title=item.title,
        content=item.content,
        source_agent=item.source_agent,
        priority=item.priority,
        metadata=item.metadata_json or {},
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _job_record(item: RagOfflineJobORM) -> RagOfflineJobRecord:
    return RagOfflineJobRecord(
        id=item.id,
        job_type=item.job_type,
        status=item.status,
        docs_dir=item.docs_dir,
        args=item.args or {},
        log_path=item.log_path,
        pid=item.pid,
        error_message=item.error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def get_by_id(self, user_id: str):
        with self.session_factory() as session:
            item = session.get(UserORM, user_id)
            return _user_record(item) if item else None

    async def get_by_username(self, username: str):
        with self.session_factory() as session:
            item = session.query(UserORM).filter(UserORM.username == username).first()
            return _user_record(item) if item else None

    async def save(self, user):
        with self.session_factory() as session:
            item = session.get(UserORM, user.id)
            if item is None:
                item = UserORM(id=user.id)
                session.add(item)
            item.username = user.username
            item.role = user.role.value if hasattr(user.role, "value") else str(user.role)
            item.tenant_id = user.tenant_id
            item.password_hash = user.password_hash
            item.created_at = user.created_at
            session.commit()
            session.refresh(item)
            return _user_record(item)


class SQLAlchemySessionRepository(SessionRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def get(self, session_id: str):
        with self.session_factory() as session:
            item = session.get(SessionORM, session_id)
            return _session_record(item) if item else None

    async def save(self, session_record):
        with self.session_factory() as session:
            item = session.get(SessionORM, session_record.id)
            if item is None:
                item = SessionORM(id=session_record.id)
                session.add(item)
                item.started_at = session_record.started_at
            item.user_id = session_record.user_id
            item.live_room_id = session_record.live_room_id
            item.current_product_id = session_record.current_product_id
            item.live_stage = (
                session_record.live_stage.value
                if hasattr(session_record.live_stage, "value")
                else str(session_record.live_stage)
            )
            item.status = session_record.status.value if hasattr(session_record.status, "value") else str(session_record.status)
            item.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(item)
            return _session_record(item)

    async def list_recent(self, limit: int = 20) -> list[SessionRecord]:
        with self.session_factory() as session:
            items = session.query(SessionORM).order_by(desc(SessionORM.updated_at)).limit(limit).all()
            return [_session_record(item) for item in items]


class SQLAlchemyMessageRepository(MessageRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, message):
        with self.session_factory() as session:
            item = MessageORM(
                id=message.id,
                session_id=message.session_id,
                role=message.role.value if hasattr(message.role, "value") else str(message.role),
                content=message.content,
                intent=message.intent.value if getattr(message, "intent", None) is not None and hasattr(message.intent, "value") else getattr(message, "intent", None),
                agent_name=message.agent_name,
                metadata_json=message.metadata or {},
                created_at=message.created_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _message_record(item)

    async def list_by_session(self, session_id: str):
        with self.session_factory() as session:
            items = (
                session.query(MessageORM)
                .filter(MessageORM.session_id == session_id)
                .order_by(MessageORM.created_at.asc())
                .all()
            )
            return [_message_record(item) for item in items]


class SQLAlchemyKnowledgeRepository(KnowledgeRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, document):
        with self.session_factory() as session:
            item = KnowledgeDocumentORM(
                id=document.id,
                title=document.title,
                source_type=document.source_type,
                product_id=document.product_id,
                content=document.content,
                metadata_json=document.metadata or {},
                version=document.version,
                is_active=document.is_active,
                created_at=document.created_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _knowledge_record(item)

    async def list_active(self):
        with self.session_factory() as session:
            items = session.query(KnowledgeDocumentORM).filter(KnowledgeDocumentORM.is_active.is_(True)).all()
            return [_knowledge_record(item) for item in items]


class SQLAlchemyToolCallLogRepository(ToolCallLogRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, log):
        with self.session_factory() as session:
            item = ToolCallLogORM(
                id=log.id,
                session_id=log.session_id,
                trace_id=log.trace_id,
                tool_name=log.tool_name,
                node_name=log.node_name,
                category=log.category,
                input_payload=log.input_payload or {},
                output_summary=log.output_summary,
                latency_ms=log.latency_ms,
                status=log.status,
                created_at=log.created_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _tool_log_record(item)

    async def list_recent(self, limit: int = 100) -> list[ToolCallLogRecord]:
        with self.session_factory() as session:
            items = session.query(ToolCallLogORM).order_by(desc(ToolCallLogORM.created_at)).limit(limit).all()
            return [_tool_log_record(item) for item in items]

    async def list_by_trace(self, trace_id: str) -> list[ToolCallLogRecord]:
        with self.session_factory() as session:
            items = (
                session.query(ToolCallLogORM)
                .filter(ToolCallLogORM.trace_id == trace_id)
                .order_by(ToolCallLogORM.created_at.asc())
                .all()
            )
            return [_tool_log_record(item) for item in items]

    async def aggregate_metrics(self, limit: int = 500) -> dict[str, Any]:
        items = await self.list_recent(limit)
        by_node: dict[str, list[int]] = defaultdict(list)
        by_status: Counter[str] = Counter()
        by_category: Counter[str] = Counter()
        degraded_count = 0
        error_count = 0
        intercept_count = 0

        for item in items:
            by_node[item.node_name or "unknown"].append(item.latency_ms)
            by_status[item.status] += 1
            by_category[item.category] += 1
            if item.status == "degraded":
                degraded_count += 1
            if item.status in {"error", "failed"}:
                error_count += 1
            if item.status == "intercepted":
                intercept_count += 1

        node_p95 = {}
        for node_name, values in by_node.items():
            values = sorted(values)
            if not values:
                node_p95[node_name] = 0
                continue
            index = max(0, int(len(values) * 0.95) - 1)
            node_p95[node_name] = values[index]

        return {
            "recent_count": len(items),
            "node_p95_ms": node_p95,
            "by_status": dict(by_status),
            "by_category": dict(by_category),
            "degraded_count": degraded_count,
            "error_count": error_count,
            "intercept_count": intercept_count,
        }


class SQLAlchemyReportRepository(ReportRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, report):
        with self.session_factory() as session:
            item = ReportORM(
                id=report.id,
                session_id=report.session_id,
                summary=report.summary,
                total_messages=report.total_messages,
                intent_distribution=report.intent_distribution or {},
                top_questions=report.top_questions or [],
                unresolved_questions=report.unresolved_questions or [],
                hot_products=report.hot_products or [],
                script_usage=report.script_usage or [],
                suggestions=report.suggestions or [],
                created_at=report.created_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _report_record(item)

    async def get(self, report_id: str) -> ReportRecord | None:
        with self.session_factory() as session:
            item = session.get(ReportORM, report_id)
            return _report_record(item) if item else None

    async def list_recent(self, limit: int = 50) -> list[ReportRecord]:
        with self.session_factory() as session:
            items = session.query(ReportORM).order_by(desc(ReportORM.created_at)).limit(limit).all()
            return [_report_record(item) for item in items]


class SQLAlchemyHighFrequencyQuestionRepository(HighFrequencyQuestionRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def upsert_many(
        self,
        product_id: str,
        questions: list[str],
        source_session_id: str | None = None,
    ) -> list[HighFrequencyQuestionRecord]:
        if not product_id:
            return []

        with self.session_factory() as session:
            updated: list[HighFrequencyQuestionRecord] = []
            for question in questions:
                normalized = " ".join(question.lower().split())
                item = (
                    session.query(HighFrequencyQuestionORM)
                    .filter(
                        HighFrequencyQuestionORM.product_id == product_id,
                        HighFrequencyQuestionORM.normalized_question == normalized,
                    )
                    .first()
                )
                if item is None:
                    item = HighFrequencyQuestionORM(
                        product_id=product_id,
                        question=question,
                        normalized_question=normalized,
                        source_session_id=source_session_id,
                    )
                    session.add(item)
                else:
                    item.frequency += 1
                    item.updated_at = datetime.utcnow()
                session.flush()
                updated.append(_hfq_record(item))
            session.commit()
            return updated

    async def list_by_product(self, product_id: str, limit: int = 10) -> list[HighFrequencyQuestionRecord]:
        with self.session_factory() as session:
            items = (
                session.query(HighFrequencyQuestionORM)
                .filter(HighFrequencyQuestionORM.product_id == product_id)
                .order_by(desc(HighFrequencyQuestionORM.frequency), desc(HighFrequencyQuestionORM.updated_at))
                .limit(limit)
                .all()
            )
            return [_hfq_record(item) for item in items]


class SQLAlchemyAgentPreferenceRepository(AgentPreferenceRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def get_by_user_id(self, user_id: str) -> AgentPreferenceRecord | None:
        with self.session_factory() as session:
            item = session.query(AgentPreferenceORM).filter(AgentPreferenceORM.user_id == user_id).first()
            return _preference_record(item) if item else None

    async def save(self, record: AgentPreferenceRecord) -> AgentPreferenceRecord:
        with self.session_factory() as session:
            item = session.query(AgentPreferenceORM).filter(AgentPreferenceORM.user_id == record.user_id).first()
            if item is None:
                item = AgentPreferenceORM(id=record.id, user_id=record.user_id)
                session.add(item)
            item.script_style = record.script_style
            item.custom_sensitive_terms = record.custom_sensitive_terms or []
            item.metadata_json = record.metadata or {}
            item.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(item)
            return _preference_record(item)


class SQLAlchemyLiveBarrageEventRepository(LiveBarrageEventRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, record: LiveBarrageEventRecord) -> LiveBarrageEventRecord:
        with self.session_factory() as session:
            item = LiveBarrageEventORM(
                id=record.id,
                session_id=record.session_id,
                user_id=record.user_id,
                display_name=record.display_name,
                text=record.text,
                source=record.source,
                metadata_json=record.metadata or {},
                created_at=record.created_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _live_barrage_record(item)

    async def list_recent_by_session(self, session_id: str, limit: int = 50) -> list[LiveBarrageEventRecord]:
        with self.session_factory() as session:
            items = (
                session.query(LiveBarrageEventORM)
                .filter(LiveBarrageEventORM.session_id == session_id)
                .order_by(desc(LiveBarrageEventORM.created_at))
                .limit(limit)
                .all()
            )
            return [_live_barrage_record(item) for item in items]


class SQLAlchemyTeleprompterItemRepository(TeleprompterItemRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, record: TeleprompterItemRecord) -> TeleprompterItemRecord:
        with self.session_factory() as session:
            item = TeleprompterItemORM(
                id=record.id,
                session_id=record.session_id,
                title=record.title,
                content=record.content,
                source_agent=record.source_agent,
                priority=record.priority,
                metadata_json=record.metadata or {},
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _teleprompter_record(item)

    async def get_latest_by_session(self, session_id: str) -> TeleprompterItemRecord | None:
        with self.session_factory() as session:
            item = (
                session.query(TeleprompterItemORM)
                .filter(TeleprompterItemORM.session_id == session_id)
                .order_by(desc(TeleprompterItemORM.updated_at), desc(TeleprompterItemORM.created_at))
                .first()
            )
            return _teleprompter_record(item) if item else None


class SQLAlchemyRagOfflineJobRepository(RagOfflineJobRepository):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    async def create(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        with self.session_factory() as session:
            item = RagOfflineJobORM(
                id=record.id,
                job_type=record.job_type,
                status=record.status,
                docs_dir=record.docs_dir,
                args=record.args or {},
                log_path=record.log_path,
                pid=record.pid,
                error_message=record.error_message,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _job_record(item)

    async def get(self, job_id: str) -> RagOfflineJobRecord | None:
        with self.session_factory() as session:
            item = session.get(RagOfflineJobORM, job_id)
            return _job_record(item) if item else None

    async def save(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        with self.session_factory() as session:
            item = session.get(RagOfflineJobORM, record.id)
            if item is None:
                item = RagOfflineJobORM(id=record.id)
                session.add(item)
                item.created_at = record.created_at
            item.job_type = record.job_type
            item.status = record.status
            item.docs_dir = record.docs_dir
            item.args = record.args or {}
            item.log_path = record.log_path
            item.pid = record.pid
            item.error_message = record.error_message
            item.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(item)
            return _job_record(item)

    async def list_recent(self, limit: int = 20) -> list[RagOfflineJobRecord]:
        with self.session_factory() as session:
            items = (
                session.query(RagOfflineJobORM)
                .order_by(desc(RagOfflineJobORM.created_at))
                .limit(limit)
                .all()
            )
            return [_job_record(item) for item in items]
