import asyncio
import json

from app.agents.analyst_agent import AnalystAgent
from app.agents.script_agent import ScriptAgent
from app.schemas.domain import IntentType, MessageRecord, MessageRole, SessionRecord, SessionStatus


class StubScriptRouterAgent:
    async def run(self, state):
        _ = state
        return {
            "intent": "script",
            "intent_confidence": 0.97,
            "route_reason": "stub route to script",
            "route_target": "script",
            "requires_retrieval": True,
            "knowledge_scope": "mixed",
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubAnalystRouterAgent:
    async def run(self, state):
        _ = state
        return {
            "intent": "analyst",
            "intent_confidence": 0.99,
            "route_reason": "stub route to analyst",
            "route_target": "analyst",
            "requires_retrieval": False,
            "knowledge_scope": "mixed",
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubScriptResult:
    def __init__(self, doc_id: str, content: str, final_score: float = 0.92, source_type: str = "product_detail"):
        self.doc_id = doc_id
        self.content = content
        self.final_score = final_score
        self.source_type = source_type
        self.metadata = {"source_file": "product_detail.md"}


class StubScriptPipeline:
    def __init__(self):
        self.last_query = None
        self.last_source_hint = None

    async def retrieve(self, query: str, source_hint: str | None = None):
        self.last_query = query
        self.last_source_hint = source_hint
        return "context", [
            StubScriptResult("doc-1", "这款拖洗一体机主打高温蒸汽去污和拖吸一体。"),
            StubScriptResult("doc-2", "当前直播间优惠即将结束，库存紧张。"),
        ]


class StubScriptLLM:
    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
        return {
            "script_type": "promotion",
            "tone": "promotional",
            "reason": "当前诉求明显是促单口播。",
            "content": "宝宝们这波库存不多了，现在下单更划算。",
            "candidates": [
                "宝宝们这波库存不多了，现在下单更划算。",
                "今晚优惠快结束了，喜欢的现在就可以拍。",
                "这个价格很难再等到，想要的别犹豫。",
            ],
        }


class StubAnalystLLM:
    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
        return {
            "summary": "本场用户主要关注商品卖点与售后问题，整体问答链路稳定。",
            "suggestions": [
                "把高频问题提前整理成主播提示卡。",
                "补齐售后类标准回答，减少 unresolved。",
                "把表现好的促单话术沉淀成模板。",
            ],
        }


def _extract_final_payload(sse_text: str) -> dict:
    current_event = None
    for line in sse_text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
            continue
        if current_event == "final" and line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError("final SSE event not found")


def _seed_session(container, session_id: str, product_id: str = "SKU-1", status: SessionStatus = SessionStatus.active):
    asyncio.run(
        container.session_repository.save(
            SessionRecord(
                id=session_id,
                user_id="seed-user",
                current_product_id=product_id,
                status=status,
            )
        )
    )


def _seed_message(container, message: MessageRecord):
    asyncio.run(container.message_repository.create(message))


def test_chat_stream_runs_real_script_agent_chain(client, auth_headers):
    session_id = "script-api-session"
    container = client.app.state.container
    _seed_session(container, session_id)

    pipeline = StubScriptPipeline()
    container.graph_runtime.router_agent = StubScriptRouterAgent()
    container.graph_runtime.script_agent = ScriptAgent(
        retrieval_pipeline=pipeline,
        llm_client=StubScriptLLM(),
    )

    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "user_input": "帮我来一段促单话术，强调库存快没了。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
            "hot_keywords": ["库存", "优惠"],
            "script_style": "促销型",
        },
    )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: final" in response.text
    assert "库存不多了" in response.text
    assert pipeline.last_source_hint == "mixed"

    final_payload = _extract_final_payload(response.text)
    assert final_payload["intent"] == "script"
    assert final_payload["guardrail_pass"] is True
    assert final_payload["message"]["metadata"]["script_type"] == "promotion"
    assert final_payload["message"]["metadata"]["script_tone"] == "promotional"
    assert len(final_payload["message"]["metadata"]["script_candidates"]) == 3

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages", headers=auth_headers)
    assert messages_response.status_code == 200
    messages = messages_response.json()["data"]
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert assistant_messages[-1]["metadata"]["script_type"] == "promotion"


def test_chat_stream_runs_real_analyst_agent_chain(client, auth_headers):
    session_id = "analyst-api-session"
    container = client.app.state.container
    _seed_session(container, session_id, status=SessionStatus.ended)
    _seed_message(
        container,
        MessageRecord(session_id=session_id, role=MessageRole.user, content="这款适合什么家庭用？"),
    )
    _seed_message(
        container,
        MessageRecord(
            session_id=session_id,
            role=MessageRole.assistant,
            content="适合有孩子和养宠家庭。",
            intent=IntentType.qa,
            metadata={"unresolved": False},
        ),
    )
    _seed_message(
        container,
        MessageRecord(session_id=session_id, role=MessageRole.user, content="坏了怎么保修？"),
    )
    _seed_message(
        container,
        MessageRecord(
            session_id=session_id,
            role=MessageRole.assistant,
            content="建议联系客服确认。",
            intent=IntentType.qa,
            metadata={"unresolved": True},
        ),
    )
    _seed_message(
        container,
        MessageRecord(
            session_id=session_id,
            role=MessageRole.assistant,
            content="库存不多了，现在下单更划算。",
            intent=IntentType.script,
            metadata={"script_type": "promotion"},
        ),
    )

    container.graph_runtime.router_agent = StubAnalystRouterAgent()
    container.graph_runtime.analyst_agent = AnalystAgent(
        message_repository=container.message_repository,
        session_repository=container.session_repository,
        report_repository=container.report_repository,
        llm_client=StubAnalystLLM(),
    )

    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "user_input": "帮我生成今晚的复盘报告。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
    )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: final" in response.text
    assert "整体问答链路稳定" in response.text

    final_payload = _extract_final_payload(response.text)
    assert final_payload["intent"] == "analyst"
    assert final_payload["guardrail_pass"] is True
    analyst_report = final_payload["message"]["metadata"]["analyst_report"]
    assert analyst_report["total_messages"] == 5
    assert analyst_report["top_questions"][0] == "这款适合什么家庭用？"
    assert analyst_report["unresolved_questions"] == ["坏了怎么保修？"]
    assert analyst_report["script_usage"] == [{"script_type": "promotion", "count": 1}]
    assert final_payload["message"]["metadata"]["report_id"]

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages", headers=auth_headers)
    assert messages_response.status_code == 200
    messages = messages_response.json()["data"]
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert assistant_messages[-1]["metadata"]["analyst_report"]["hot_products"] == ["SKU-1"]
