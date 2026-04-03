from __future__ import annotations

from app.agents.qa_agent import ChatOpenAIJsonClient, QAAgent
from app.core.config import settings
from app.memory.memory_policy import MemoryPolicy
from app.memory.memory_service import LongTermMemoryService
from app.memory.qa_agent_memory_hook import QAMemoryHook


def build_qa_agent_with_memory() -> QAAgent:
    """Example factory showing how to wire Mem0 only into QA Agent."""

    qa_agent = QAAgent(
        retrieval_pipeline=None,
        llm_client=ChatOpenAIJsonClient(label="qa"),
    )

    memory_service = LongTermMemoryService.from_mem0_config(
        api_key=settings.MEM0_API_KEY,
        base_url=settings.MEM0_BASE_URL,
        org_id=settings.MEM0_ORG_ID,
        project_id=settings.MEM0_PROJECT_ID,
        enabled=settings.QA_MEMORY_ENABLED,
        similarity_threshold=settings.QA_MEMORY_THRESHOLD,
    )
    memory_hook = QAMemoryHook(
        memory_service=memory_service,
        policy=MemoryPolicy(),
        agent_id=settings.QA_MEMORY_AGENT_ID,
        app_id=settings.QA_MEMORY_APP_ID,
        top_k=settings.QA_MEMORY_TOP_K,
        threshold=settings.QA_MEMORY_THRESHOLD,
    )
    qa_agent.bind_memory_hook(memory_hook)
    return qa_agent
