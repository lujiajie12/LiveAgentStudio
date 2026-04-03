import pytest

from app.agents.router import RouterAgent


class StubGateway:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    async def ainvoke_tool_call(self, system_prompt: str, user_prompt: str, tools):
        _ = system_prompt, user_prompt, tools
        if self.error:
            raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_router_agent_falls_back_on_parse_error():
    agent = RouterAgent(StubGateway(error=ValueError("bad json")))
    result = await agent.run(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "这个商品怎么样，适合什么家庭使用？",
            "live_stage": "intro",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["requires_retrieval"] is True
    assert result["planner_action"] == "retrieve_knowledge"
    assert result["intent_confidence"] == 0.72
    assert result["route_fallback_reason"] == "planner_error"
    assert result["route_low_confidence"] is True


@pytest.mark.asyncio
async def test_router_agent_fast_routes_short_unclear_query_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={
                "tool_name": "handoff_agent",
                "arguments": {
                    "agent": "direct",
                    "intent": "unknown",
                    "knowledge_scope": "mixed",
                    "reason": "short vague direct query",
                },
            }
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "说点什么",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "unknown"
    assert result["route_target"] == "direct"
    assert result["requires_retrieval"] is False
    assert result["planner_action"] == "handoff_agent"
    assert result["route_low_confidence"] is False


@pytest.mark.asyncio
async def test_router_agent_fast_routes_noise_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={
                "tool_name": "handoff_agent",
                "arguments": {
                    "agent": "direct",
                    "intent": "unknown",
                    "knowledge_scope": "mixed",
                    "reason": "noise",
                },
            }
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-2",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "1111",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "unknown"
    assert result["route_target"] == "direct"
    assert result["requires_retrieval"] is False
    assert result["planner_action"] == "handoff_agent"


@pytest.mark.asyncio
async def test_router_agent_routes_live_context_question_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={
                "tool_name": "handoff_agent",
                "arguments": {
                    "agent": "direct",
                    "intent": "qa",
                    "knowledge_scope": "mixed",
                    "reason": "live context question",
                },
            }
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-3",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "今天这场直播主推什么？",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "direct"
    assert result["requires_retrieval"] is False
    assert result["planner_action"] == "handoff_agent"


@pytest.mark.asyncio
async def test_router_agent_routes_datetime_question_to_qa_without_retrieval():
    agent = RouterAgent(
        StubGateway(payload={"tool_name": "call_datetime", "arguments": {"reason": "datetime"}})
    )
    result = await agent.run(
        {
            "trace_id": "trace-3b",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "今天是周几？",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["requires_retrieval"] is False
    assert result["tool_intent"] == "datetime"
    assert result["planner_action"] == "call_datetime"


@pytest.mark.asyncio
async def test_router_agent_routes_web_search_question_to_qa_without_retrieval():
    agent = RouterAgent(
        StubGateway(
            payload={
                "tool_name": "call_web_search",
                "arguments": {"query": "今日黄金金价是多少？", "reason": "search"},
            }
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-3c",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "今日黄金金价是多少？",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["requires_retrieval"] is False
    assert result["tool_intent"] == "web_search"
    assert result["planner_action"] == "call_web_search"


@pytest.mark.asyncio
async def test_router_agent_routes_memory_recall_question_to_qa_without_retrieval():
    agent = RouterAgent(
        StubGateway(payload={"tool_name": "recall_memory", "arguments": {"reason": "memory"}})
    )
    result = await agent.run(
        {
            "trace_id": "trace-3d",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "刚刚我问你的是什么问题？",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["requires_retrieval"] is False
    assert result["tool_intent"] == "memory_recall"
    assert result["planner_action"] == "recall_memory"


@pytest.mark.asyncio
async def test_router_agent_keeps_product_question_on_rag_path():
    agent = RouterAgent(
        StubGateway(
            payload={
                "tool_name": "retrieve_knowledge",
                "arguments": {
                    "query": "这款洗地机适合什么家庭使用？",
                    "knowledge_scope": "product_detail",
                    "reason": "product detail question",
                },
            }
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-4",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "这款洗地机适合什么家庭使用？",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["requires_retrieval"] is True
    assert result["planner_action"] == "retrieve_knowledge"
