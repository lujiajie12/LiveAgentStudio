import pytest

from app.agents.analyst_agent import AnalystAgent
from app.repositories.in_memory import InMemoryMessageRepository, InMemoryReportRepository, InMemorySessionRepository
from app.schemas.domain import IntentType, MessageRecord, MessageRole, SessionRecord, SessionStatus


class StubLLM:
    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
        return {
            "summary": "本场用户问题集中在商品卖点和售后说明，整体沟通链路稳定。",
            "suggestions": [
                "把高频问题提前整理成主播提示卡。",
                "补齐售后类标准回答，减少 unresolved。",
                "把表现好的促单话术沉淀成模板。",
            ],
        }


@pytest.mark.asyncio
async def test_analyst_agent_builds_report_and_persists_it():
    message_repository = InMemoryMessageRepository()
    session_repository = InMemorySessionRepository()
    report_repository = InMemoryReportRepository()
    await session_repository.save(
        SessionRecord(
            id="session-1",
            user_id="user-1",
            current_product_id="SKU-1",
            status=SessionStatus.ended,
        )
    )
    await message_repository.create(
        MessageRecord(session_id="session-1", role=MessageRole.user, content="这款适合什么家庭用？")
    )
    await message_repository.create(
        MessageRecord(
            session_id="session-1",
            role=MessageRole.assistant,
            content="适合有孩子和养宠家庭。",
            intent=IntentType.qa,
            metadata={"unresolved": False},
        )
    )
    await message_repository.create(
        MessageRecord(session_id="session-1", role=MessageRole.user, content="坏了怎么保修？")
    )
    await message_repository.create(
        MessageRecord(
            session_id="session-1",
            role=MessageRole.assistant,
            content="建议联系客服确认。",
            intent=IntentType.qa,
            metadata={"unresolved": True},
        )
    )
    await message_repository.create(
        MessageRecord(
            session_id="session-1",
            role=MessageRole.assistant,
            content="库存不多了，现在下单更划算。",
            intent=IntentType.script,
            metadata={"script_type": "promotion"},
        )
    )

    agent = AnalystAgent(
        message_repository=message_repository,
        session_repository=session_repository,
        report_repository=report_repository,
        llm_client=StubLLM(),
    )

    result = await agent.run(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_role": "operator",
            "user_input": "帮我生成今晚的复盘报告。",
            "live_stage": "closing",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
        }
    )

    assert result["agent_name"] == "analyst"
    assert result["report_id"] is not None
    assert result["analyst_report"]["total_messages"] == 5
    assert result["analyst_report"]["top_questions"][0] == "这款适合什么家庭用？"
    assert result["analyst_report"]["unresolved_questions"] == ["坏了怎么保修？"]
    assert result["analyst_report"]["hot_products"] == ["SKU-1"]
    assert result["analyst_report"]["script_usage"] == [{"script_type": "promotion", "count": 1}]
    assert report_repository.reports[0].summary.startswith("本场用户问题集中")
