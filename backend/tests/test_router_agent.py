import json

import pytest

from app.agents.direct_reply_agent import DirectReplyAgent
from app.agents.router import RouterAgent


class StubGateway:
    """Stub for router tests. Router now calls ainvoke_text and expects a JSON string."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        if self.error:
            raise self.error
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)

    def _heuristic_response(self, user_prompt: str):
        """Delegate to real heuristic for fallback tests."""
        from app.services.llm_gateway import OpenAILLMGateway
        gw = OpenAILLMGateway.__new__(OpenAILLMGateway)
        return gw._heuristic_response(user_prompt)


class StubDirectLLM:
    def __init__(self, text: str):
        self.text = text

    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt, user_prompt
        return self.text


@pytest.mark.asyncio
async def test_direct_reply_agent_returns_llm_answer_instead_of_fallback():
    agent = DirectReplyAgent(llm_client=StubDirectLLM("我是自定义 direct 回答"))
    result = await agent.run(
        {
            "trace_id": "trace-direct-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "你是什么agent?",
            "route_target": "direct",
            "planner_mode": "function_calling",
            "route_fallback_reason": None,
        }
    )
    assert result["agent_name"] == "direct"
    assert result["agent_output"] == "我是自定义 direct 回答"


@pytest.mark.asyncio
async def test_direct_reply_agent_identity_prompt_includes_agent_disambiguation():
    captured = {}

    class CapturingDirectLLM:
        async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return "我是 LiveAgent 直播中台智能助手"

    agent = DirectReplyAgent(llm_client=CapturingDirectLLM())
    result = await agent.run(
        {
            "trace_id": "trace-direct-disambiguation",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "你是什么agent?",
            "route_target": "direct",
            "planner_mode": "function_calling",
            "route_fallback_reason": None,
        }
    )
    assert result["agent_name"] == "direct"
    assert "不是在问底层模型厂商、参数规模或模型架构" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_direct_reply_agent_fallback_when_llm_missing():
    agent = DirectReplyAgent(llm_client=None)
    result = await agent.run(
        {
            "trace_id": "trace-direct-2",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "你是什么agent?",
            "route_target": "direct",
            "planner_mode": "heuristic",
            "route_fallback_reason": "planner_error",
        }
    )
    assert result["agent_name"] == "direct"
    assert "我是 LiveAgent 直播中台智能助手" in result["agent_output"]


@pytest.mark.asyncio
async def test_direct_reply_agent_returns_provider_error_message_when_upstream_unavailable():
    class FailingDirectLLM:
        async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            raise RuntimeError("Error code: 400 - {'error': {'message': 'Access denied', 'code': 'Arrearage'}}")

    agent = DirectReplyAgent(llm_client=FailingDirectLLM())
    result = await agent.run(
        {
            "trace_id": "trace-direct-3",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "你是什么agent?",
            "route_target": "direct",
            "planner_mode": "function_calling",
            "route_fallback_reason": None,
        }
    )
    assert result["agent_name"] == "direct"
    assert "当前大模型服务暂时不可用" in result["agent_output"]


@pytest.mark.asyncio
async def test_router_agent_routes_identity_question_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "direct", "tool_action": None, "reason": "system identity question"}
        )
    )
    result = await agent.run(
        {
            "trace_id": "trace-identity",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "你是什么agent?",
            "live_stage": "pitch",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "direct"
    assert result["route_target"] == "direct"
    assert result["route_low_confidence"] is False


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
    # Heuristic fallback should classify product question as qa
    assert result["intent"] == "qa"
    assert result["route_target"] == "qa"
    assert result["route_low_confidence"] is True


@pytest.mark.asyncio
async def test_router_agent_fast_routes_short_unclear_query_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "direct", "tool_action": None, "reason": "short vague direct query"}
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
    assert result["intent"] == "direct"
    assert result["route_target"] == "direct"
    assert result["route_low_confidence"] is False


@pytest.mark.asyncio
async def test_router_agent_fast_routes_noise_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "direct", "tool_action": None, "reason": "noise"}
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
    assert result["intent"] == "direct"
    assert result["route_target"] == "direct"


@pytest.mark.asyncio
async def test_router_agent_routes_live_context_question_to_direct():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "direct", "tool_action": None, "reason": "live context question"}
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
    assert result["route_target"] == "direct"


@pytest.mark.asyncio
async def test_router_agent_routes_datetime_question_to_executor():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "executor", "tool_action": "call_datetime", "reason": "datetime query"}
        )
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
    assert result["route_target"] == "executor"
    assert result["tool_intent"] == "datetime"
    assert result["planner_action"] == "call_datetime"


@pytest.mark.asyncio
async def test_router_agent_routes_web_search_question_to_executor():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "executor", "tool_action": "call_web_search", "reason": "search query"}
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
    assert result["route_target"] == "executor"
    assert result["tool_intent"] == "web_search"
    assert result["planner_action"] == "call_web_search"


@pytest.mark.asyncio
async def test_router_agent_routes_memory_recall_question_to_executor():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "executor", "tool_action": "recall_memory", "reason": "memory recall"}
        )
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
    assert result["route_target"] == "executor"
    assert result["tool_intent"] == "memory_recall"
    assert result["planner_action"] == "recall_memory"


@pytest.mark.asyncio
async def test_router_agent_keeps_product_question_on_qa_path():
    agent = RouterAgent(
        StubGateway(
            payload={"route": "qa", "tool_action": None, "reason": "product detail question"}
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
    assert result["route_low_confidence"] is False
