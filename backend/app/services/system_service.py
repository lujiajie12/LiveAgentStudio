from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.infra.database import ping_database
from app.repositories.base import ToolCallLogRepository
from app.services.memory_service import MemoryService


class SystemService:
    def __init__(
        self,
        *,
        db_engine,
        memory_service: MemoryService,
        bm25_index,
        vector_index,
        tool_log_repository: ToolCallLogRepository,
    ):
        self.db_engine = db_engine
        self.memory_service = memory_service
        self.bm25_index = bm25_index
        self.vector_index = vector_index
        self.tool_log_repository = tool_log_repository

    async def get_health(self) -> dict[str, Any]:
        postgres_ok = ping_database(self.db_engine)
        redis_ok = await self.memory_service.ping()
        bm25_health = await self.bm25_index.health()
        vector_health = await self.vector_index.health()
        llm_status = "ok" if (settings.LLM_API_KEY or settings.OPENAI_API_KEY) else "degraded"

        services = {
            "api": {"status": "ok"},
            "postgres": {"status": "ok" if postgres_ok else "degraded"},
            "redis": {"status": "ok" if redis_ok else "degraded"},
            "memory": {
                "status": "ok" if redis_ok else "degraded",
                "reason": None if redis_ok else "redis_unavailable",
            },
            "bm25": bm25_health,
            "vector_store": vector_health,
            "llm": {
                "status": llm_status,
                "model": settings.LLM_MODEL or settings.ROUTER_MODEL,
            },
        }
        overall = "ok" if all(item["status"] == "ok" for item in services.values()) else "degraded"
        return {"status": overall, "services": services}

    async def get_metrics(self) -> dict[str, Any]:
        metrics = await self.tool_log_repository.aggregate_metrics(settings.METRICS_LOG_SAMPLE_LIMIT)
        return {
            "status": "ok",
            "window_size": settings.METRICS_LOG_SAMPLE_LIMIT,
            "metrics": metrics,
        }
