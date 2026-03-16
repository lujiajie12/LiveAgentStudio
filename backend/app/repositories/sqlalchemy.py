from app.repositories.base import (
    KnowledgeRepository,
    MessageRepository,
    ReportRepository,
    SessionRepository,
    ToolCallLogRepository,
    UserRepository,
)


class SQLAlchemyUserRepository(UserRepository):
    async def get_by_id(self, user_id: str):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")

    async def get_by_username(self, username: str):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")

    async def save(self, user):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")


class SQLAlchemySessionRepository(SessionRepository):
    async def get(self, session_id: str):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")

    async def save(self, session):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")


class SQLAlchemyMessageRepository(MessageRepository):
    async def create(self, message):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")

    async def list_by_session(self, session_id: str):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")


class SQLAlchemyKnowledgeRepository(KnowledgeRepository):
    async def create(self, document):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")

    async def list_active(self):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")


class SQLAlchemyToolCallLogRepository(ToolCallLogRepository):
    async def create(self, log):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")


class SQLAlchemyReportRepository(ReportRepository):
    async def create(self, report):
        raise NotImplementedError("SQLAlchemy repositories are placeholders in MVP scaffold")
