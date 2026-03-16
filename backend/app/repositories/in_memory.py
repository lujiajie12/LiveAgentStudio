from app.repositories.base import (
    KnowledgeRepository,
    MessageRepository,
    ReportRepository,
    SessionRepository,
    ToolCallLogRepository,
    UserRepository,
)
from app.schemas.domain import (
    KnowledgeDocumentRecord,
    MessageRecord,
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
        self.sessions[session.id] = session
        return session


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


class InMemoryReportRepository(ReportRepository):
    def __init__(self):
        self.reports: list[ReportRecord] = []

    async def create(self, report: ReportRecord) -> ReportRecord:
        self.reports.append(report)
        return report
