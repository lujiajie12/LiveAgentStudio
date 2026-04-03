from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


try:  # pragma: no cover - optional dependency
    from mem0 import AsyncMemoryClient
except ImportError:  # pragma: no cover
    AsyncMemoryClient = None


@dataclass(slots=True)
class MemoryRecord:
    memory_id: str
    memory: str
    score: float
    metadata: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None
    raw: dict[str, Any] | None = None


class MemoryBackend(Protocol):
    async def add(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str,
        agent_id: str,
        app_id: str,
        run_id: str,
        metadata: dict[str, Any],
    ) -> Any:
        ...

    async def search(self, query: str, *, user_id: str, top_k: int) -> Any:
        ...

    async def get_all(self, *, user_id: str | None = None) -> Any:
        ...

    async def delete(self, memory_id: str) -> Any:
        ...


class InMemoryMem0Backend:
    """Simple in-memory backend for tests and local fallback."""

    def __init__(self):
        self._items: dict[str, dict[str, Any]] = {}

    async def add(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str,
        agent_id: str,
        app_id: str,
        run_id: str,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        memory_id = str(uuid.uuid4())
        memory_text = " ".join(str(item.get("content", "")).strip() for item in messages if item.get("content"))
        record = {
            "id": memory_id,
            "memory": memory_text,
            "metadata": {
                **metadata,
                "scope_user_id": user_id,
                "scope_agent_id": agent_id,
                "scope_app_id": app_id,
                "scope_run_id": run_id,
            },
            "created_at": now,
            "updated_at": now,
        }
        self._items[memory_id] = record
        return [record]

    async def search(self, query: str, *, user_id: str, top_k: int) -> list[dict[str, Any]]:
        normalized_query = self._tokenize(query)
        results: list[dict[str, Any]] = []
        for item in self._items.values():
            if item["metadata"].get("scope_user_id") != user_id:
                continue
            score = self._score(normalized_query, self._tokenize(item.get("memory", "")))
            if score <= 0:
                continue
            results.append({**item, "score": score})
        results.sort(key=lambda entry: entry.get("score", 0.0), reverse=True)
        return results[:top_k]

    async def get_all(self, *, user_id: str | None = None) -> list[dict[str, Any]]:
        items = list(self._items.values())
        if user_id is None:
            return items
        return [item for item in items if item["metadata"].get("scope_user_id") == user_id]

    async def delete(self, memory_id: str) -> bool:
        return self._items.pop(memory_id, None) is not None

    def _tokenize(self, text: str) -> set[str]:
        normalized = re.sub(r"[，。！？；、,:;!?()\[\]{}]+", " ", str(text or "").lower())
        tokens = {token for token in normalized.split() if token}
        cjk_text = re.sub(r"\s+", "", normalized)
        tokens.update(char for char in cjk_text if "\u4e00" <= char <= "\u9fff")
        return tokens

    def _score(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        shared = left & right
        if not shared:
            return 0.0
        return len(shared) / math.sqrt(len(left) * len(right))


class Mem0PlatformBackend:
    """Async wrapper around the Mem0 platform client."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ):
        if AsyncMemoryClient is None:  # pragma: no cover
            raise RuntimeError("mem0ai[async] is not installed")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["host"] = base_url
        if org_id:
            client_kwargs["org_id"] = org_id
        if project_id:
            client_kwargs["project_id"] = project_id
        self.client = AsyncMemoryClient(**client_kwargs)

    async def add(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str,
        agent_id: str,
        app_id: str,
        run_id: str,
        metadata: dict[str, Any],
    ) -> Any:
        return await self.client.add(
            messages,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
            metadata=metadata,
        )

    async def search(self, query: str, *, user_id: str, top_k: int) -> Any:
        try:
            return await self.client.search(query, user_id=user_id, top_k=top_k)
        except TypeError:  # pragma: no cover - SDK compatibility shim
            return await self.client.search(query, user_id=user_id, limit=top_k)

    async def get_all(self, *, user_id: str | None = None) -> Any:
        if user_id:
            try:
                return await self.client.get_all(user_id=user_id)
            except TypeError:  # pragma: no cover
                return await self.client.get_all(filters={"user_id": user_id})
        return await self.client.get_all()

    async def delete(self, memory_id: str) -> Any:
        try:
            return await self.client.delete(memory_id)
        except TypeError:  # pragma: no cover
            return await self.client.delete(memory_id=memory_id)


class LongTermMemoryService:
    """Facade used by QA Agent for Mem0-backed long-term memory."""

    def __init__(
        self,
        *,
        backend: MemoryBackend | None = None,
        enabled: bool = False,
        similarity_threshold: float = 0.45,
    ):
        self.backend = backend
        self.enabled = enabled and backend is not None
        self.similarity_threshold = similarity_threshold

    @classmethod
    def from_mem0_config(
        cls,
        *,
        api_key: str | None,
        base_url: str | None,
        org_id: str | None,
        project_id: str | None,
        enabled: bool,
        similarity_threshold: float,
    ) -> "LongTermMemoryService":
        if not enabled or not api_key:
            return cls(enabled=False, similarity_threshold=similarity_threshold)
        backend = Mem0PlatformBackend(
            api_key=api_key,
            base_url=base_url,
            org_id=org_id,
            project_id=project_id,
        )
        return cls(backend=backend, enabled=True, similarity_threshold=similarity_threshold)

    async def add_memory(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        agent_id: str,
        app_id: str,
        run_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        if not self.enabled or not self.backend or not messages:
            return []
        scoped_metadata = {
            **dict(metadata or {}),
            "scope_user_id": user_id,
            "scope_agent_id": agent_id,
            "scope_app_id": app_id,
            "scope_run_id": run_id,
        }
        try:
            raw = await self.backend.add(
                messages,
                user_id=user_id,
                agent_id=agent_id,
                app_id=app_id,
                run_id=run_id,
                metadata=scoped_metadata,
            )
            return self._normalize_records(raw)
        except Exception:
            return []

    async def search_memory(
        self,
        query: str,
        user_id: str,
        agent_id: str,
        app_id: str,
        top_k: int,
        *,
        threshold: float | None = None,
    ) -> list[MemoryRecord]:
        if not self.enabled or not self.backend or not query.strip():
            return []
        try:
            raw = await self.backend.search(query, user_id=user_id, top_k=max(top_k * 4, top_k))
        except Exception:
            return []
        normalized = self._normalize_records(raw)
        floor = self.similarity_threshold if threshold is None else threshold
        filtered = [
            item
            for item in normalized
            if self._matches_scope(item, user_id=user_id, agent_id=agent_id, app_id=app_id) and item.score >= floor
        ]
        filtered.sort(key=lambda item: item.score, reverse=True)
        return filtered[:top_k]

    async def get_memories(self, filters: dict[str, Any]) -> list[MemoryRecord]:
        if not self.enabled or not self.backend:
            return []
        user_id = self._string_or_none(filters.get("user_id"))
        try:
            raw = await self.backend.get_all(user_id=user_id)
        except Exception:
            return []
        normalized = self._normalize_records(raw)
        return [item for item in normalized if self._record_matches_filters(item, filters)]

    async def delete_memories(self, filters: dict[str, Any]) -> int:
        if not self.enabled or not self.backend:
            return 0
        deleted = 0
        for item in await self.get_memories(filters):
            try:
                await self.backend.delete(item.memory_id)
                deleted += 1
            except Exception:
                continue
        return deleted

    def _normalize_records(self, payload: Any) -> list[MemoryRecord]:
        if payload is None:
            return []
        raw_items = payload.get("results", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return []

        normalized: list[MemoryRecord] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                MemoryRecord(
                    memory_id=str(item.get("id") or item.get("memory_id") or ""),
                    memory=str(item.get("memory") or item.get("text") or item.get("content") or "").strip(),
                    score=float(item.get("score") or item.get("similarity") or 0.0),
                    metadata=dict(item.get("metadata") or {}),
                    created_at=self._string_or_none(item.get("created_at")),
                    updated_at=self._string_or_none(item.get("updated_at")),
                    raw=item,
                )
            )
        return normalized

    def _matches_scope(self, item: MemoryRecord, *, user_id: str, agent_id: str, app_id: str) -> bool:
        return (
            item.metadata.get("scope_user_id") == user_id
            and item.metadata.get("scope_agent_id") == agent_id
            and item.metadata.get("scope_app_id") == app_id
        )

    def _record_matches_filters(self, item: MemoryRecord, filters: dict[str, Any]) -> bool:
        metadata = item.metadata
        for key, expected in filters.items():
            if expected in (None, ""):
                continue
            actual = None
            if key == "user_id":
                actual = metadata.get("scope_user_id")
            elif key == "agent_id":
                actual = metadata.get("scope_agent_id")
            elif key == "app_id":
                actual = metadata.get("scope_app_id")
            elif key == "run_id":
                actual = metadata.get("scope_run_id")
            else:
                actual = metadata.get(key)
            if actual != expected:
                return False
        return True

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
