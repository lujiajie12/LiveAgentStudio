from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from app.core.observability import record_timed_tool_call
from app.repositories.base import MessageRepository

try:
    from redis import asyncio as redis_async
except ImportError:  # pragma: no cover
    redis_async = None


class InMemoryRedisClient:
    def __init__(self):
        self._strings: dict[str, tuple[str, float | None]] = {}
        self._hashes: dict[str, tuple[dict[str, str], float | None]] = {}

    def _alive(self, expires_at: float | None) -> bool:
        return expires_at is None or expires_at > time.time()

    async def ping(self) -> bool:
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        expires_at = time.time() + ex if ex else None
        self._strings[key] = (value, expires_at)

    async def get(self, key: str) -> str | None:
        payload = self._strings.get(key)
        if payload is None:
            return None
        value, expires_at = payload
        if not self._alive(expires_at):
            self._strings.pop(key, None)
            return None
        return value

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        payload = self._hashes.get(key)
        current, expires_at = payload if payload else ({}, None)
        if not self._alive(expires_at):
            current = {}
            expires_at = None
        current.update(mapping)
        self._hashes[key] = (current, expires_at)

    async def hgetall(self, key: str) -> dict[str, str]:
        payload = self._hashes.get(key)
        if payload is None:
            return {}
        value, expires_at = payload
        if not self._alive(expires_at):
            self._hashes.pop(key, None)
            return {}
        return dict(value)

    async def expire(self, key: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        if key in self._strings:
            value, _ = self._strings[key]
            self._strings[key] = (value, expires_at)
        if key in self._hashes:
            value, _ = self._hashes[key]
            self._hashes[key] = (value, expires_at)


def build_redis_client(redis_url: str):
    if redis_url.startswith("memory://") or redis_async is None:
        return InMemoryRedisClient()
    return redis_async.from_url(redis_url, decode_responses=True)


class MemoryService:
    def __init__(
        self,
        message_repository: MessageRepository,
        window_size: int,
        redis_client: Any | None = None,
        ttl_seconds: int = 7200,
        hot_keywords_ttl_seconds: int = 120,
    ):
        self.message_repository = message_repository
        self.window_size = window_size
        self.redis_client = redis_client or InMemoryRedisClient()
        self.ttl_seconds = ttl_seconds
        self.hot_keywords_ttl_seconds = hot_keywords_ttl_seconds

    def _memory_key(self, session_id: str) -> str:
        return f"memory:{session_id}"

    def _hot_keywords_key(self, session_id: str) -> str:
        return f"memory:{session_id}:hot_keywords"

    async def get_short_term_memory(self, session_id: str) -> list[dict[str, str]]:
        snapshot = await self.get_memory_snapshot(session_id)
        return snapshot["turns"]

    async def get_memory_snapshot(self, session_id: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            turns = await self._read_turns_from_redis(session_id)
            if turns:
                hot_keywords = await self._read_hot_keywords_from_redis(session_id)
                memory_hash = await self.redis_client.hgetall(self._memory_key(session_id))
                await record_timed_tool_call(
                    "redis_memory_read",
                    started_at=started_at,
                    node_name="memory",
                    category="memory",
                    status="ok",
                )
                return {
                    "turns": turns,
                    "current_product_id": memory_hash.get("current_product_id") or None,
                    "live_stage": memory_hash.get("live_stage") or None,
                    "hot_keywords": hot_keywords,
                    "updated_at": memory_hash.get("updated_at") or None,
                    "status": "ok",
                }
        except Exception:
            await record_timed_tool_call(
                "redis_memory_read",
                started_at=started_at,
                node_name="memory",
                category="memory",
                status="degraded",
            )

        turns = await self._fallback_turns(session_id)
        return {
            "turns": turns,
            "current_product_id": None,
            "live_stage": None,
            "hot_keywords": [],
            "updated_at": None,
            "status": "degraded",
        }

    async def refresh_short_term_memory(
        self,
        session_id: str,
        current_product_id: str | None,
        live_stage: str | None,
        hot_keywords: list[str] | None,
    ) -> None:
        started_at = time.perf_counter()
        turns = await self._fallback_turns(session_id)
        turns = turns[-self.window_size :]
        try:
            await self.redis_client.hset(
                self._memory_key(session_id),
                mapping={
                    "turns": json.dumps(turns, ensure_ascii=False),
                    "current_product_id": current_product_id or "",
                    "live_stage": live_stage or "",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            await self.redis_client.expire(self._memory_key(session_id), self.ttl_seconds)
            keywords = [str(item).strip() for item in hot_keywords or [] if str(item).strip()][:5]
            await self.redis_client.set(
                self._hot_keywords_key(session_id),
                json.dumps(keywords, ensure_ascii=False),
                ex=self.hot_keywords_ttl_seconds,
            )
            await record_timed_tool_call(
                "redis_memory_write",
                started_at=started_at,
                node_name="memory",
                category="memory",
                status="ok",
            )
        except Exception:
            await record_timed_tool_call(
                "redis_memory_write",
                started_at=started_at,
                node_name="memory",
                category="memory",
                status="degraded",
            )

    async def ping(self) -> bool:
        try:
            await self.redis_client.ping()
            return True
        except Exception:
            return False

    async def _read_turns_from_redis(self, session_id: str) -> list[dict[str, str]]:
        memory_hash = await self.redis_client.hgetall(self._memory_key(session_id))
        raw_turns = memory_hash.get("turns")
        if not raw_turns:
            return []
        turns = json.loads(raw_turns)
        if not isinstance(turns, list):
            return []
        return [
            {"role": str(item.get("role", "")), "content": str(item.get("content", ""))}
            for item in turns
            if isinstance(item, dict)
        ]

    async def _read_hot_keywords_from_redis(self, session_id: str) -> list[str]:
        raw = await self.redis_client.get(self._hot_keywords_key(session_id))
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    async def _fallback_turns(self, session_id: str) -> list[dict[str, str]]:
        messages = await self.message_repository.list_by_session(session_id)
        trimmed = messages[-self.window_size :]
        return [{"role": message.role.value, "content": message.content} for message in trimmed]
