import json

import pytest

from app.agents.base import BaseAgent
from app.agents.router import RouterAgent
from app.infra.container import build_container


class StubRouterAgent:
    def __init__(self, intent: str):
        self.intent = intent

    async def route(self, state):
        return await self.run(state)

    async def run(self, state):
        route_target = "direct" if self.intent == "unknown" else self.intent
        return {
            "intent": self.intent,
            "intent_confidence": 0.95,
            "route_reason": f"stub route to {self.intent}",
            "route_target": route_target,
            "requires_retrieval": self.intent in {"qa", "script"},
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


class StubDirectAgent(BaseAgent):
    name = "direct"

    async def run(self, state):
        return {
            "agent_output": f"direct reply for {state['user_input']}",
            "references": [],
            "retrieved_docs": [],
            "agent_name": self.name,
        }


class SequentialPlannerAgent:
    async def route(self, state):
        return await self.run(state)

    async def run(self, state):
        if state.get("retrieved_docs"):
            return {
                "intent": "qa",
                "intent_confidence": 0.95,
                "route_reason": "handoff qa after retrieval",
                "route_target": "qa",
                "requires_retrieval": False,
                "knowledge_scope": "product_detail",
                "tool_intent": "none",
                "planner_mode": "function_calling",
                "planner_action": "handoff_agent",
                "planner_action_args": {
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": "product_detail",
                },
                "planner_step_count": int(state.get("planner_step_count", 0) or 0) + 1,
                "planner_trace": list(state.get("planner_trace", []))
                + [{"planner_action": "handoff_agent", "route_target": "qa"}],
                "planning_completed": False,
                "route_fallback_reason": None,
                "route_low_confidence": False,
                "agent_name": "router",
            }
        return {
            "intent": "qa",
            "intent_confidence": 0.95,
            "route_reason": "retrieve first",
            "route_target": "qa",
            "requires_retrieval": True,
            "knowledge_scope": "product_detail",
            "tool_intent": "none",
            "planner_mode": "function_calling",
            "planner_action": "retrieve_knowledge",
            "planner_action_args": {
                "query": state["user_input"],
                "knowledge_scope": "product_detail",
            },
            "planner_step_count": int(state.get("planner_step_count", 0) or 0) + 1,
            "planner_trace": list(state.get("planner_trace", []))
            + [{"planner_action": "retrieve_knowledge", "route_target": "qa"}],
            "planning_completed": False,
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubRetrievalAwareQAAgent(BaseAgent):
    name = "qa"

    async def retrieve_only(self, state):
        return {
            "rewritten_query": state["user_input"],
            "retrieved_docs": [{"doc_id": "doc-1", "content": "stub retrieval content", "score": 0.9}],
        }

    async def run(self, state):
        return {
            "rewritten_query": state.get("rewritten_query", state["user_input"]),
            "agent_output": "stub qa answer from planner loop",
            "references": ["doc-1"],
            "retrieved_docs": list(state.get("retrieved_docs", [])),
            "qa_confidence": 0.93,
            "unresolved": False,
            "agent_name": self.name,
        }


class SequentialWebSearchPlannerAgent:
    async def route(self, state):
        return await self.run(state)

    async def run(self, state):
        if state.get("tool_outputs"):
            return {
                "intent": "qa",
                "intent_confidence": 0.95,
                "route_reason": "handoff qa after web search observation",
                "route_target": "qa",
                "requires_retrieval": False,
                "knowledge_scope": "mixed",
                "tool_intent": "web_search",
                "planner_mode": "function_calling",
                "planner_action": "handoff_agent",
                "planner_action_args": {
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": "mixed",
                },
                "planner_step_count": int(state.get("planner_step_count", 0) or 0) + 1,
                "planner_trace": list(state.get("planner_trace", []))
                + [{"planner_action": "handoff_agent", "route_target": "qa"}],
                "planning_completed": False,
                "route_fallback_reason": None,
                "route_low_confidence": False,
                "agent_name": "router",
            }
        return {
            "intent": "qa",
            "intent_confidence": 0.95,
            "route_reason": "web search first",
            "route_target": "qa",
            "requires_retrieval": False,
            "knowledge_scope": "mixed",
            "tool_intent": "web_search",
            "planner_mode": "function_calling",
            "planner_action": "call_web_search",
            "planner_action_args": {
                "query": state["user_input"],
            },
            "planner_step_count": int(state.get("planner_step_count", 0) or 0) + 1,
            "planner_trace": list(state.get("planner_trace", []))
            + [{"planner_action": "call_web_search", "route_target": "qa"}],
            "planning_completed": False,
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class AlwaysWebSearchGateway:
    def __init__(self):
        self.calls = 0

    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt, user_prompt
        self.calls += 1
        return json.dumps(
            {"route": "executor", "tool_action": "call_web_search", "reason": "always search"},
            ensure_ascii=False,
        )


class StubWebSearchAwareQAAgent(BaseAgent):
    name = "qa"

    def __init__(self):
        self.web_search_queries: list[str] = []
        self.run_states: list[dict] = []

    async def web_search_only(self, state):
        rewritten_query = state.get("rewritten_query", state["user_input"])
        self.web_search_queries.append(rewritten_query)
        return {
            "rewritten_query": rewritten_query,
            "tools_used": ["google_search"],
            "tool_outputs": {
                "google_search": {
                    "query": rewritten_query,
                    "answer_box": {
                        "answer": "今日黄金价格约为每克 728 元。",
                        "link": "https://example.com/gold",
                    },
                    "organic_results": [],
                }
            },
        }

    async def run(self, state):
        self.run_states.append(dict(state))
        return {
            "rewritten_query": state.get("rewritten_query", state["user_input"]),
            "agent_output": "stub qa answer from web search loop",
            "references": ["https://example.com/gold"],
            "retrieved_docs": [{"doc_id": "https://example.com/gold", "content": "stub web result"}],
            "qa_confidence": 0.94,
            "unresolved": False,
            "agent_name": self.name,
            "tools_used": ["google_search"],
            "tool_outputs": dict(state.get("tool_outputs", {})),
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
async def test_graph_runtime_routes_unknown_to_direct_reply():
    container = build_container()
    container.graph_runtime.router_agent = StubRouterAgent("unknown")
    container.graph_runtime.direct_agent = StubDirectAgent()

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
    assert result["agent_name"] == "direct"
    assert result["final_output"] == "direct reply for How is the weather today?"


@pytest.mark.asyncio
async def test_graph_runtime_supports_planner_executor_loop_for_qa():
    container = build_container()
    container.graph_runtime.router_agent = SequentialPlannerAgent()
    container.graph_runtime.qa_agent = StubRetrievalAwareQAAgent()

    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-3",
            "session_id": "session-3",
            "user_id": "user-1",
            "user_input": "这款适合什么家庭使用？",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )

    assert result["intent"] == "qa"
    assert result["agent_name"] == "qa"
    assert result["final_output"] == "stub qa answer from planner loop"
    assert result["references"] == ["doc-1"]


@pytest.mark.asyncio
async def test_graph_runtime_supports_planner_executor_loop_for_web_search():
    container = build_container()
    qa_agent = StubWebSearchAwareQAAgent()
    container.graph_runtime.router_agent = SequentialWebSearchPlannerAgent()
    container.graph_runtime.qa_agent = qa_agent

    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-4",
            "session_id": "session-4",
            "user_id": "user-1",
            "user_input": "今日黄金金价是多少？",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )

    assert qa_agent.web_search_queries == ["今日黄金金价是多少？"]
    assert len(qa_agent.run_states) == 1
    assert "google_search" in qa_agent.run_states[0]["tool_outputs"]
    assert result["intent"] == "qa"
    assert result["agent_name"] == "qa"
    assert result["final_output"] == "stub qa answer from web search loop"
    assert result["references"] == ["https://example.com/gold"]
    assert result["executor_observations"][-1]["kind"] == "call_web_search"


@pytest.mark.asyncio
async def test_graph_runtime_router_hands_off_after_web_search_observation():
    container = build_container()
    gateway = AlwaysWebSearchGateway()
    qa_agent = StubWebSearchAwareQAAgent()
    container.graph_runtime.router_agent = RouterAgent(gateway)
    container.graph_runtime.qa_agent = qa_agent

    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-router-loop-guard",
            "session_id": "session-router-loop-guard",
            "user_id": "user-1",
            "user_input": "今日黄金金价是多少？",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )

    assert gateway.calls == 1
    assert qa_agent.web_search_queries == ["今日黄金金价是多少？"]
    assert len(qa_agent.run_states) == 1
    assert result["intent"] == "qa"
    assert result["agent_name"] == "qa"
    assert result["final_output"] == "stub qa answer from web search loop"
    assert result["executor_observations"][-1]["kind"] == "call_web_search"
