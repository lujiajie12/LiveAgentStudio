import pytest

from app.repositories.in_memory import (
    InMemoryMessageRepository,
    InMemorySessionRepository,
    InMemoryToolCallLogRepository,
)
from app.schemas.chat import ChatStreamRequest
from app.schemas.domain import LiveStage
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService


class StubGraphRuntime:
    async def ainvoke(self, state):
        _ = state
        return {
            "intent": "qa",
            "agent_name": "qa",
            "final_output": "stub final answer",
            "guardrail_pass": True,
            "route_reason": "stub route",
            "route_target": "qa",
            "requires_retrieval": True,
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "knowledge_scope": "product_detail",
            "rewritten_query": "rewritten question",
            "qa_confidence": 0.84,
            "references": ["doc-1"],
            "unresolved": False,
        }


@pytest.mark.asyncio
async def test_chat_service_persists_qa_metadata():
    message_repository = InMemoryMessageRepository()
    service = ChatService(
        graph_runtime=StubGraphRuntime(),
        session_repository=InMemorySessionRepository(),
        message_repository=message_repository,
        memory_service=MemoryService(message_repository, window_size=5),
        tool_log_repository=InMemoryToolCallLogRepository(),
    )

    result, assistant = await service.run_chat(
        request=ChatStreamRequest(
            session_id="session-1",
            user_input="这款适合什么家庭用？",
            current_product_id="SKU-1",
            live_stage=LiveStage.pitch,
        ),
        user_id="user-1",
        trace_id="trace-1",
    )

    assert result["intent"] == "qa"
    assert assistant.metadata["rewritten_query"] == "rewritten question"
    assert assistant.metadata["qa_confidence"] == 0.84
    assert assistant.metadata["references"] == ["doc-1"]
    assert assistant.metadata["unresolved"] is False
    assert assistant.metadata["route_target"] == "qa"
    assert assistant.metadata["requires_retrieval"] is True
