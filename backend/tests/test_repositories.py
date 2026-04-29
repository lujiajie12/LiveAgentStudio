import pytest

from app.repositories.in_memory import InMemoryMessageRepository
from app.schemas.domain import MessageRecord, MessageRole


@pytest.mark.asyncio
async def test_in_memory_message_repository_crud():
    repository = InMemoryMessageRepository()
    created = await repository.create(
        MessageRecord(session_id="session-1", role=MessageRole.user, content="hello")
    )

    items = await repository.list_by_session("session-1")
    assert len(items) == 1
    assert items[0].id == created.id
