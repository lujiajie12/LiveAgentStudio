from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graph.state import LiveAgentState
from app.memory.memory_policy import MemoryPolicy
from app.memory.memory_service import LongTermMemoryService, MemoryRecord


@dataclass(slots=True)
class QAMemoryHook:
    """QA-only long-term memory integration wrapper."""

    memory_service: LongTermMemoryService
    policy: MemoryPolicy
    agent_id: str
    app_id: str
    top_k: int = 4
    threshold: float = 0.45

    async def search_for_state(self, state: LiveAgentState) -> list[MemoryRecord]:
        # 相似度搜索用于“当前问题需要借鉴历史偏好/FAQ/商品事实”的场景。
        user_id = str(state.get("user_id") or "").strip()
        query = str(state.get("user_input") or "").strip()
        app_id = str(state.get("app_id") or self.app_id).strip() or self.app_id
        if not user_id or not query:
            return []
        return await self.memory_service.search_memory(
            query=query,
            user_id=user_id,
            agent_id=self.agent_id,
            app_id=app_id,
            top_k=self.top_k,
            threshold=self.threshold,
        )

    # 记忆回溯类问题更适合直接拿最近记忆，而不是拿当前问句做相似度搜索。
    async def list_recent_for_state(self, state: LiveAgentState, limit: int = 3) -> list[MemoryRecord]:
        user_id = str(state.get("user_id") or "").strip()
        app_id = str(state.get("app_id") or self.app_id).strip() or self.app_id
        if not user_id:
            return []
        records = await self.memory_service.get_memories(
            {
                "user_id": user_id,
                "agent_id": self.agent_id,
                "app_id": app_id,
            }
        )
        records.sort(key=lambda item: item.updated_at or item.created_at or "", reverse=True)
        return records[:limit]

    def build_prompt_context(self, memories: list[MemoryRecord]) -> str:
        # 长期记忆进入 LLM 前先压成稳定文本块，避免不同调用方重复做 prompt 拼装。
        if not memories:
            return ""
        lines = ["Relevant long-term QA memories for this same user scope:"]
        for index, item in enumerate(memories, start=1):
            summary = str(item.metadata.get("memory_summary") or item.memory).strip()
            memory_types = item.metadata.get("memory_types") or []
            type_block = ",".join(str(entry) for entry in memory_types if str(entry).strip())
            parts = [f"{index}. score={item.score:.2f}"]
            if type_block:
                parts.append(f"types={type_block}")
            parts.append(f"memory={summary}")
            lines.append("; ".join(parts))
        return "\n".join(lines)

    def serialize_memories(self, memories: list[MemoryRecord]) -> list[dict[str, Any]]:
        return [
            {
                "memory_id": item.memory_id,
                "memory": item.memory,
                "score": item.score,
                "metadata": item.metadata,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in memories
        ]

    async def remember_qa_interaction(
        self,
        *,
        user_input: str,
        assistant_output: str,
        user_id: str,
        run_id: str,
        current_product_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        # 长期记忆写入统一经过 policy，避免把噪声、时效性问题、元问题直接落库。
        if not self.memory_service.enabled:
            return False
        decision = self.policy.build_write_decision(
            user_input=user_input,
            assistant_output=assistant_output,
            current_product_id=current_product_id,
            metadata=metadata,
        )
        if not decision.should_store or not decision.messages:
            return False

        await self.memory_service.add_memory(
            messages=decision.messages,
            user_id=user_id,
            agent_id=self.agent_id,
            app_id=self.app_id,
            run_id=run_id,
            metadata=decision.metadata,
        )
        return True
