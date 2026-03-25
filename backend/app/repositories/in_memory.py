from collections import Counter
from datetime import datetime
from typing import Any

from app.repositories.base import (
    AgentPreferenceRepository,
    HighFrequencyQuestionRepository,
    KnowledgeRepository,
    MessageRepository,
    RagOfflineJobRepository,
    ReportRepository,
    SessionRepository,
    ToolCallLogRepository,
    UserRepository,
)
from app.schemas.domain import (
    AgentPreferenceRecord,
    HighFrequencyQuestionRecord,
    KnowledgeDocumentRecord,
    MessageRecord,
    RagOfflineJobRecord,
    ReportRecord,
    SessionRecord,
    ToolCallLogRecord,
    UserRecord,
)


class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self.users: dict[str, UserRecord] = {}

    async def get_by_id(self, user_id: str) -> UserRecord | None:
        return self.users.get(user_id)

    async def get_by_username(self, username: str) -> UserRecord | None:
        return next((user for user in self.users.values() if user.username == username), None)

    async def save(self, user: UserRecord) -> UserRecord:
        self.users[user.id] = user
        return user


class InMemorySessionRepository(SessionRepository):
    def __init__(self):
        self.sessions: dict[str, SessionRecord] = {}

    async def get(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)

    async def save(self, session: SessionRecord) -> SessionRecord:
        session.updated_at = datetime.utcnow()
        self.sessions[session.id] = session
        return session

    async def list_recent(self, limit: int = 20) -> list[SessionRecord]:
        return sorted(self.sessions.values(), key=lambda item: item.updated_at, reverse=True)[:limit]


class InMemoryMessageRepository(MessageRepository):
    def __init__(self):
        self.messages: list[MessageRecord] = []

    async def create(self, message: MessageRecord) -> MessageRecord:
        self.messages.append(message)
        return message

    async def list_by_session(self, session_id: str) -> list[MessageRecord]:
        return [message for message in self.messages if message.session_id == session_id]


class InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self):
        self.documents: dict[str, KnowledgeDocumentRecord] = {}

    async def create(self, document: KnowledgeDocumentRecord) -> KnowledgeDocumentRecord:
        self.documents[document.id] = document
        return document

    async def list_active(self) -> list[KnowledgeDocumentRecord]:
        return [doc for doc in self.documents.values() if doc.is_active]


class InMemoryToolCallLogRepository(ToolCallLogRepository):
    def __init__(self):
        self.logs: list[ToolCallLogRecord] = []

    async def create(self, log: ToolCallLogRecord) -> ToolCallLogRecord:
        self.logs.append(log)
        return log

    async def list_recent(self, limit: int = 100) -> list[ToolCallLogRecord]:
        return sorted(self.logs, key=lambda item: item.created_at, reverse=True)[:limit]

    async def list_by_trace(self, trace_id: str) -> list[ToolCallLogRecord]:
        return [log for log in self.logs if log.trace_id == trace_id]

    async def aggregate_metrics(self, limit: int = 500) -> dict[str, Any]:
        items = await self.list_recent(limit)
        node_counter = Counter(log.node_name or "unknown" for log in items)
        status_counter = Counter(log.status for log in items)
        degraded_count = sum(1 for log in items if log.status == "degraded")
        error_count = sum(1 for log in items if log.status in {"error", "failed"})
        return {
            "recent_count": len(items),
            "by_node": dict(node_counter),
            "by_status": dict(status_counter),
            "degraded_count": degraded_count,
            "error_count": error_count,
        }


class InMemoryReportRepository(ReportRepository):
    def __init__(self):
        self.reports: list[ReportRecord] = []

    async def create(self, report: ReportRecord) -> ReportRecord:
        self.reports.append(report)
        return report

    async def get(self, report_id: str) -> ReportRecord | None:
        return next((report for report in self.reports if report.id == report_id), None)

    async def list_recent(self, limit: int = 50) -> list[ReportRecord]:
        return sorted(self.reports, key=lambda item: item.created_at, reverse=True)[:limit]


class InMemoryHighFrequencyQuestionRepository(HighFrequencyQuestionRepository):
    def __init__(self):
        self.records: list[HighFrequencyQuestionRecord] = []

    async def upsert_many(
        self,
        product_id: str,
        questions: list[str],
        source_session_id: str | None = None,
    ) -> list[HighFrequencyQuestionRecord]:
        updated: list[HighFrequencyQuestionRecord] = []
        for question in questions:
            normalized = " ".join(question.lower().split())
            existing = next(
                (
                    item
                    for item in self.records
                    if item.product_id == product_id and item.normalized_question == normalized
                ),
                None,
            )
            if existing is None:
                existing = HighFrequencyQuestionRecord(
                    product_id=product_id,
                    question=question,
                    normalized_question=normalized,
                    source_session_id=source_session_id,
                )
                self.records.append(existing)
            else:
                existing.frequency += 1
                existing.updated_at = datetime.utcnow()
            updated.append(existing)
        return updated

    async def list_by_product(self, product_id: str, limit: int = 10) -> list[HighFrequencyQuestionRecord]:
        matches = [item for item in self.records if item.product_id == product_id]
        return sorted(matches, key=lambda item: (-item.frequency, item.updated_at), reverse=False)[:limit]


class InMemoryAgentPreferenceRepository(AgentPreferenceRepository):
    def __init__(self):
        self.records: dict[str, AgentPreferenceRecord] = {}

    async def get_by_user_id(self, user_id: str) -> AgentPreferenceRecord | None:
        return self.records.get(user_id)

    async def save(self, record: AgentPreferenceRecord) -> AgentPreferenceRecord:
        record.updated_at = datetime.utcnow()
        self.records[record.user_id] = record
        return record


class InMemoryRagOfflineJobRepository(RagOfflineJobRepository):
    def __init__(self):
        self.records: dict[str, RagOfflineJobRecord] = {}

    async def create(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        self.records[record.id] = record
        return record

    async def get(self, job_id: str) -> RagOfflineJobRecord | None:
        return self.records.get(job_id)

    async def save(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        record.updated_at = datetime.utcnow()
        self.records[record.id] = record
        return record

    async def list_recent(self, limit: int = 20) -> list[RagOfflineJobRecord]:
        return sorted(self.records.values(), key=lambda item: item.created_at, reverse=True)[:limit]
