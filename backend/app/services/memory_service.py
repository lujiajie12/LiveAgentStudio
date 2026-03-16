from app.repositories.base import MessageRepository


class MemoryService:
    def __init__(self, message_repository: MessageRepository, window_size: int):
        self.message_repository = message_repository
        self.window_size = window_size

    async def get_short_term_memory(self, session_id: str) -> list[dict[str, str]]:
        messages = await self.message_repository.list_by_session(session_id)
        trimmed = messages[-self.window_size :]
        return [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in trimmed
        ]
