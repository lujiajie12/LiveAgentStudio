import asyncio
import json

from app.core.config import settings
from app.schemas.chat import ChatEvent


def format_sse_event(event: ChatEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


class StreamingService:
    def __init__(self, chunk_size: int, event_delay_ms: int):
        self.chunk_size = chunk_size
        self.event_delay_ms = event_delay_ms

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []
        return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

    async def stream_text(self, trace_id: str, session_id: str, text: str):
        yield format_sse_event(
            ChatEvent(
                event="meta",
                data={"trace_id": trace_id, "session_id": session_id},
            )
        )

        for chunk in self.chunk_text(text):
            yield format_sse_event(ChatEvent(event="token", data={"content": chunk}))
            await asyncio.sleep(settings.SSE_EVENT_DELAY_MS / 1000)

        yield format_sse_event(ChatEvent(event="final", data={"content": text}))
