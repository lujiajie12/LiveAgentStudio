import pytest

from app.agents.router import RouterAgent


class StubGateway:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
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
            "user_input": "这个商品怎么样",
            "live_stage": "intro",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "qa"
    assert result["intent_confidence"] == 0.0
    assert result["route_fallback_reason"] == "parse_error"


@pytest.mark.asyncio
async def test_router_agent_marks_low_confidence():
    agent = RouterAgent(
        StubGateway(
            payload={
                "intent": "script",
                "confidence": 0.3,
                "reason": "uncertain",
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
    assert result["intent"] == "qa"
    assert result["route_low_confidence"] is True
