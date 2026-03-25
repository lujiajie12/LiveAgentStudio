import pytest

from app.agents.base import BaseAgent
from app.infra.container import build_container


class StubRouterAgent:
    def __init__(self, intent: str):
        self.intent = intent

    async def run(self, state):
        return {
            "intent": self.intent,
            "intent_confidence": 0.95,
            "route_reason": f"stub route to {self.intent}",
            "knowledge_scope": "mixed",
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubQAAgent(BaseAgent):
    name = "qa"

    async def run(self, state):
        return {
            "rewritten_query": state["user_input"],
            "agent_output": "stub qa answer",
            "references": ["doc-1"],
            "retrieved_docs": [{"doc_id": "doc-1", "content": "stub"}],
            "qa_confidence": 0.91,
            "unresolved": False,
            "agent_name": self.name,
        }


class StubScriptAgent(BaseAgent):
    name = "script"

    async def run(self, state):
        return {
            "agent_output": "stub script answer",
            "references": [],
            "retrieved_docs": [],
            "agent_name": self.name,
        }


@pytest.mark.asyncio
async def test_graph_runtime_routes_script_requests():
    container = build_container()
    container.graph_runtime.router_agent = StubRouterAgent("script")
    container.graph_runtime.script_agent = StubScriptAgent()

    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "Please help me write a short sales script.",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )

    assert result["intent"] == "script"
    assert result["agent_name"] == "script"
    assert result["final_output"] == "stub script answer"


@pytest.mark.asyncio
async def test_graph_runtime_routes_unknown_to_qa():
    container = build_container()
    container.graph_runtime.router_agent = StubRouterAgent("unknown")
    container.graph_runtime.qa_agent = StubQAAgent()

    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-2",
            "session_id": "session-2",
            "user_id": "user-1",
            "user_input": "How is the weather today?",
            "live_stage": "warmup",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )

    assert result["intent"] == "unknown"
    assert result["agent_name"] == "qa"
    assert result["final_output"] == "stub qa answer"
