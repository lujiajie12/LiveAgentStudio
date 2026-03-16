from abc import ABC, abstractmethod

from app.schemas.domain import (
    KnowledgeDocumentRecord,
    MessageRecord,
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


class ReportRepository(ABC):
    @abstractmethod
    async def create(self, report: ReportRecord) -> ReportRecord:
        raise NotImplementedError
