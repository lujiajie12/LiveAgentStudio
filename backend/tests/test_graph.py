import pytest

from app.infra.container import build_container


@pytest.mark.asyncio
async def test_graph_runtime_routes_script_requests():
    container = build_container()
    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "帮我写一段促单话术",
            "live_stage": "pitch",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "script"
    assert "Script Agent" in result["final_output"]


@pytest.mark.asyncio
async def test_graph_runtime_routes_unknown_to_qa():
    container = build_container()
    result = await container.graph_runtime.ainvoke(
        {
            "trace_id": "trace-2",
            "session_id": "session-2",
            "user_id": "user-1",
            "user_input": "今天天气怎么样",
            "live_stage": "warmup",
            "current_product_id": None,
            "short_term_memory": [],
        }
    )
    assert result["intent"] == "unknown"
    assert "QA Agent" in result["final_output"]
