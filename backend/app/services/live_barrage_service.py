from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.repositories.base import LiveBarrageEventRepository, SessionRepository, ToolCallLogRepository
from app.schemas.domain import (
    LiveBarrageEventRecord,
    LiveStage,
    SessionRecord,
    SessionStatus,
    ToolCallLogRecord,
)


class LiveBarrageService:
    def __init__(
        self,
        *,
        redis_client: Any,
        barrage_repository: LiveBarrageEventRepository,
        session_repository: SessionRepository,
        tool_log_repository: ToolCallLogRepository,
        recent_limit: int = 50,
        active_window_minutes: int = 5,
    ):
        self.redis_client = redis_client
        self.barrage_repository = barrage_repository
        self.session_repository = session_repository
        self.tool_log_repository = tool_log_repository
        self.recent_limit = recent_limit
        self.active_window_minutes = active_window_minutes
        self._listeners: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def _recent_key(self, session_id: str) -> str:
        return f"live:barrages:{session_id}:recent"

    def _overview_key(self, session_id: str) -> str:
        return f"live:overview:{session_id}"

    async def ingest_barrage(
        self,
        *,
        session_id: str,
        display_name: str,
        text: str,
        source: str,
        requested_by: str,
        user_id: str | None = None,
        created_at: datetime | None = None,
        current_product_id: str | None = None,
        live_stage: str | None = None,
        online_viewers: int | None = None,
        conversion_rate: float | None = None,
        interaction_rate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_stage = live_stage or LiveStage.intro.value
        session = await self.session_repository.get(session_id)
        if session is None:
            session = SessionRecord(
                id=session_id,
                user_id=requested_by,
                current_product_id=current_product_id,
                live_stage=normalized_stage,
                status=SessionStatus.active,
            )
        else:
            session.current_product_id = current_product_id
            session.live_stage = normalized_stage or session.live_stage
            session.updated_at = datetime.utcnow()
        await self.session_repository.save(session)

        payload = LiveBarrageEventRecord(
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            text=text.strip(),
            source=source or "simulator",
            metadata=metadata or {},
            created_at=created_at or datetime.utcnow(),
        )
        record = await self.barrage_repository.create(payload)

        recent_records = await self.barrage_repository.list_recent_by_session(session_id, limit=self.recent_limit)
        recent_records = list(reversed(recent_records))
        await self._write_recent_cache(session_id, recent_records)

        overview = await self._build_overview(
            session=session,
            recent_records=recent_records,
            online_viewers=online_viewers,
            conversion_rate=conversion_rate,
            interaction_rate=interaction_rate,
        )
        await self._write_overview_cache(session_id, overview)

        await self.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=session_id,
                tool_name="barrage_ingest",
                node_name="live",
                category="live",
                input_payload={
                    "source": source,
                    "display_name": display_name,
                    "text_length": len(text.strip()),
                },
                output_summary=text.strip()[:120],
                status="ok",
            )
        )

        await self._broadcast(
            session_id,
            {
                "type": "barrage",
                "item": self.serialize_barrage(record),
            },
        )
        await self._broadcast(
            session_id,
            {
                "type": "overview",
                "item": overview,
            },
        )
        return self.serialize_barrage(record)

    async def list_recent_barrages(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        cached = await self._read_recent_cache(session_id)
        if cached:
            return cached[-(limit or self.recent_limit) :]

        records = await self.barrage_repository.list_recent_by_session(session_id, limit=limit or self.recent_limit)
        ordered = [self.serialize_barrage(item) for item in reversed(records)]
        if ordered:
            await self.redis_client.set(
                self._recent_key(session_id),
                json.dumps(ordered, ensure_ascii=False),
                ex=3600,
            )
        return ordered

    async def get_overview(self, session_id: str) -> dict[str, Any]:
        session = await self.session_repository.get(session_id)
        recent_payload = await self.list_recent_barrages(session_id, limit=self.recent_limit)
        cached = await self._read_overview_cache(session_id)
        recent_records = [self.deserialize_barrage(item) for item in recent_payload]

        if session is None:
            session = SessionRecord(
                id=session_id,
                user_id="studio",
                current_product_id=None,
                live_stage=LiveStage.intro,
                status=SessionStatus.active,
            )

        overview = await self._build_overview(
            session=session,
            recent_records=recent_records,
            online_viewers=cached.get("online_viewers"),
            conversion_rate=cached.get("conversion_rate"),
            interaction_rate=cached.get("interaction_rate"),
        )
        overview["conversion_rate_estimated"] = bool(cached.get("conversion_rate_estimated", True))
        return overview

    async def update_overview(
        self,
        *,
        session_id: str,
        requested_by: str,
        current_product_id: str | None = None,
        live_stage: str | None = None,
        online_viewers: int | None = None,
        conversion_rate: float | None = None,
        interaction_rate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_stage = live_stage or LiveStage.intro.value
        session = await self.session_repository.get(session_id)
        if session is None:
            session = SessionRecord(
                id=session_id,
                user_id=requested_by,
                current_product_id=current_product_id,
                live_stage=normalized_stage,
                status=SessionStatus.active,
            )
        else:
            session.current_product_id = current_product_id
            session.live_stage = normalized_stage or session.live_stage
            session.updated_at = datetime.utcnow()
        await self.session_repository.save(session)

        recent_payload = await self.list_recent_barrages(session_id, limit=self.recent_limit)
        recent_records = [self.deserialize_barrage(item) for item in recent_payload]
        overview = await self._build_overview(
            session=session,
            recent_records=recent_records,
            online_viewers=online_viewers,
            conversion_rate=conversion_rate,
            interaction_rate=interaction_rate,
        )
        if metadata:
            overview["metadata"] = metadata
        await self._write_overview_cache(session_id, overview)

        await self.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=session_id,
                tool_name="live_overview_update",
                node_name="live",
                category="live",
                input_payload={
                    "current_product_id": session.current_product_id,
                    "live_stage": overview["live_stage"],
                    "online_viewers": overview["online_viewers"],
                },
                output_summary=f"viewers={overview['online_viewers']} product={overview['current_product_id'] or 'unset'}",
                status="ok",
            )
        )

        await self._broadcast(
            session_id,
            {
                "type": "overview",
                "item": overview,
            },
        )
        return overview

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
        listeners = list(self._listeners.get(session_id, set()))
        for queue in listeners:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue

    async def _write_recent_cache(self, session_id: str, records: list[LiveBarrageEventRecord]) -> None:
        payload = [self.serialize_barrage(item) for item in records][-self.recent_limit :]
        await self.redis_client.set(
            self._recent_key(session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=3600,
        )

    async def _read_recent_cache(self, session_id: str) -> list[dict[str, Any]]:
        raw = await self.redis_client.get(self._recent_key(session_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    async def _write_overview_cache(self, session_id: str, overview: dict[str, Any]) -> None:
        await self.redis_client.set(
            self._overview_key(session_id),
            json.dumps(overview, ensure_ascii=False),
            ex=3600,
        )

    async def _read_overview_cache(self, session_id: str) -> dict[str, Any]:
        raw = await self.redis_client.get(self._overview_key(session_id))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    async def _build_overview(
        self,
        *,
        session: SessionRecord,
        recent_records: list[LiveBarrageEventRecord],
        online_viewers: int | None,
        conversion_rate: float | None,
        interaction_rate: float | None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        active_since = now - timedelta(minutes=self.active_window_minutes)
        active_records = [item for item in recent_records if item.created_at >= active_since]
        active_users = {item.user_id or item.display_name for item in active_records}

        if interaction_rate is None:
            interaction_rate = round(len(active_records) / max(self.active_window_minutes, 1), 2)
        if online_viewers is None:
            online_viewers = max(len(active_users), len(active_records), 0)
        estimated = conversion_rate is None
        if conversion_rate is None:
            conversion_rate = round(min(max(interaction_rate * 0.18, 0.0), 9.99), 2)

        metrics = await self.tool_log_repository.aggregate_metrics(limit=200)
        node_p95 = metrics.get("node_p95_ms", {})
        degraded_count = metrics.get("degraded_count", 0)
        intercept_count = metrics.get("intercept_count", 0)

        return {
            "session_id": session.id,
            "online_viewers": int(online_viewers),
            "current_product_id": session.current_product_id,
            "live_stage": session.live_stage.value if hasattr(session.live_stage, "value") else str(session.live_stage),
            "interaction_rate": float(interaction_rate),
            "conversion_rate": float(conversion_rate),
            "conversion_rate_estimated": estimated,
            "barrage_count_last_window": len(active_records),
            "active_users_last_window": len(active_users),
            "updated_at": datetime.utcnow().isoformat(),
            "agent_status_summary": [
                {
                    "key": "qa",
                    "label": "RAG 知识答疑",
                    "detail": f"P95 {node_p95.get('qa') or node_p95.get('retrieval') or 0}ms",
                    "icon": "bot",
                    "status": "degraded" if degraded_count else "online",
                },
                {
                    "key": "guardrail",
                    "label": "实时风控与拦截",
                    "detail": f"拦截 {intercept_count} 次",
                    "icon": "shield-alert",
                    "status": "online",
                },
                {
                    "key": "ops",
                    "label": "运营控场编排",
                    "detail": f"最近 {metrics.get('recent_count', 0)} 条事件",
                    "icon": "activity",
                    "status": "busy" if active_records else "idle",
                },
            ],
        }

    @staticmethod
    def serialize_barrage(record: LiveBarrageEventRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "session_id": record.session_id,
            "user_id": record.user_id,
            "display_name": record.display_name,
            "user": record.display_name,
            "text": record.text,
            "source": record.source,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def deserialize_barrage(payload: dict[str, Any]) -> LiveBarrageEventRecord:
        created_at = payload.get("created_at")
        return LiveBarrageEventRecord(
            id=payload.get("id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            display_name=payload.get("display_name") or payload.get("user") or "User",
            text=payload.get("text") or "",
            source=payload.get("source") or "simulator",
            metadata=payload.get("metadata") or {},
            created_at=datetime.fromisoformat(created_at) if isinstance(created_at, str) else datetime.utcnow(),
        )
