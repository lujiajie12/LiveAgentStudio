from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.repositories.base import TeleprompterItemRepository, ToolCallLogRepository
from app.schemas.domain import TeleprompterItemRecord, ToolCallLogRecord


class TeleprompterService:
    def __init__(
        self,
        *,
        redis_client: Any,
        teleprompter_repository: TeleprompterItemRepository,
        tool_log_repository: ToolCallLogRepository,
    ):
        self.redis_client = redis_client
        self.teleprompter_repository = teleprompter_repository
        self.tool_log_repository = tool_log_repository
        self._listeners: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def _current_key(self, session_id: str) -> str:
        return f"teleprompter:{session_id}:current"

    async def push(
        self,
        *,
        session_id: str,
        title: str,
        content: str,
        source_agent: str,
        priority: str,
        requested_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = TeleprompterItemRecord(
            session_id=session_id,
            title=title.strip(),
            content=content.strip(),
            source_agent=source_agent.strip() or "qa",
            priority=priority.strip() or "normal",
            metadata=metadata or {},
            updated_at=datetime.utcnow(),
        )
        saved = await self.teleprompter_repository.create(record)
        payload = self.serialize(saved)
        await self.redis_client.set(
            self._current_key(session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=7200,
        )
        await self.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=session_id,
                tool_name="teleprompter_push",
                node_name="teleprompter",
                category="teleprompter",
                input_payload={
                    "title": saved.title,
                    "source_agent": saved.source_agent,
                    "priority": saved.priority,
                    "requested_by": requested_by,
                },
                output_summary=saved.content[:120],
                status="accepted",
            )
        )
        await self._broadcast(session_id, {"type": "teleprompter", "item": payload})
        return payload

    async def get_current(self, session_id: str) -> dict[str, Any] | None:
        raw = await self.redis_client.get(self._current_key(session_id))
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return payload

        record = await self.teleprompter_repository.get_latest_by_session(session_id)
        if record is None:
            return None
        payload = self.serialize(record)
        await self.redis_client.set(
            self._current_key(session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=7200,
        )
        return payload

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners[session_id].add(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(session_id)
        if not listeners:
            return
        listeners.discard(queue)
        if not listeners:
            self._listeners.pop(session_id, None)

    async def _broadcast(self, session_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._listeners.get(session_id, set())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue

    @staticmethod
    def serialize(record: TeleprompterItemRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "session_id": record.session_id,
            "title": record.title,
            "content": record.content,
            "source_agent": record.source_agent,
            "priority": record.priority,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
