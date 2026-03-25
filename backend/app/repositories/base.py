from abc import ABC, abstractmethod
from typing import Any

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


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> UserRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_username(self, username: str) -> UserRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, user: UserRecord) -> UserRecord:
        raise NotImplementedError


class SessionRepository(ABC):
    @abstractmethod
    async def get(self, session_id: str) -> SessionRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, session: SessionRecord) -> SessionRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int = 20) -> list[SessionRecord]:
        raise NotImplementedError


class MessageRepository(ABC):
    @abstractmethod
    async def create(self, message: MessageRecord) -> MessageRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[MessageRecord]:
        raise NotImplementedError


class KnowledgeRepository(ABC):
    @abstractmethod
    async def create(self, document: KnowledgeDocumentRecord) -> KnowledgeDocumentRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_active(self) -> list[KnowledgeDocumentRecord]:
        raise NotImplementedError


class ToolCallLogRepository(ABC):
    @abstractmethod
    async def create(self, log: ToolCallLogRecord) -> ToolCallLogRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int = 100) -> list[ToolCallLogRecord]:
        raise NotImplementedError

    @abstractmethod
    async def list_by_trace(self, trace_id: str) -> list[ToolCallLogRecord]:
        raise NotImplementedError

    @abstractmethod
    async def aggregate_metrics(self, limit: int = 500) -> dict[str, Any]:
        raise NotImplementedError


class ReportRepository(ABC):
    @abstractmethod
    async def create(self, report: ReportRecord) -> ReportRecord:
        raise NotImplementedError

    @abstractmethod
    async def get(self, report_id: str) -> ReportRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[ReportRecord]:
        raise NotImplementedError


class HighFrequencyQuestionRepository(ABC):
    @abstractmethod
    async def upsert_many(
        self,
        product_id: str,
        questions: list[str],
        source_session_id: str | None = None,
    ) -> list[HighFrequencyQuestionRecord]:
        raise NotImplementedError

    @abstractmethod
    async def list_by_product(
        self,
        product_id: str,
        limit: int = 10,
    ) -> list[HighFrequencyQuestionRecord]:
        raise NotImplementedError


class AgentPreferenceRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: str) -> AgentPreferenceRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, record: AgentPreferenceRecord) -> AgentPreferenceRecord:
        raise NotImplementedError


class RagOfflineJobRepository(ABC):
    @abstractmethod
    async def create(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        raise NotImplementedError

    @abstractmethod
    async def get(self, job_id: str) -> RagOfflineJobRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, record: RagOfflineJobRecord) -> RagOfflineJobRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int = 20) -> list[RagOfflineJobRecord]:
        raise NotImplementedError
