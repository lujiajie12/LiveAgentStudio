import asyncio
import json

from app.agents.qa_agent import QAAgent
from app.schemas.domain import MessageRecord, MessageRole


class StubRouterAgent:
    async def run(self, state):
        _ = state
        return {
            "intent": "qa",
            "intent_confidence": 0.98,
            "route_reason": "stub route to qa",
            "route_target": "qa",
            "requires_retrieval": True,
            "knowledge_scope": "product_detail",
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubMemoryRouterAgent:
    async def run(self, state):
        _ = state
        return {
            "intent": "qa",
            "intent_confidence": 0.98,
            "route_reason": "stub route to memory recall qa",
            "route_target": "qa",
            "requires_retrieval": False,
            "knowledge_scope": "mixed",
            "tool_intent": "memory_recall",
            "route_fallback_reason": None,
            "route_low_confidence": False,
            "agent_name": "router",
        }


class StubPipeline:
    def __init__(self):
        self.last_query = None
        self.last_source_hint = None

    async def retrieve(self, query: str, source_hint: str | None = None):
        self.last_query = query
        self.last_source_hint = source_hint
        return "context", [
            StubResult(
                "doc-1",
                "This product is suitable for pet owners and families with children.",
                metadata={"source_file": "product_detail.md"},
            ),
            StubResult(
                "doc-2",
                "Compared with a normal mop, it removes stains faster with steam cleaning.",
                metadata={"source_file": "product_detail.md"},
            ),
            StubResult(
                "doc-3",
                "Water tank is 650ml and cable length is 6m.",
                metadata={"source_file": "product_detail.md"},
            ),
        ]


class StubResult:
    def __init__(
        self,
        doc_id: str,
        content: str,
        final_score: float = 0.9,
        source_type: str = "product_detail",
        metadata: dict | None = None,
    ):
        self.doc_id = doc_id
        self.content = content
        self.final_score = final_score
        self.source_type = source_type
        self.metadata = metadata or {}


class StubLLM:
    def __init__(self):
        self.responses = [
            {"rewritten_query": "What is the difference between Qinglan steam mop and a normal mop?"},
            {
                "answer": "It is better for families with children or pets, and steam cleaning is stronger than a normal mop.",
                "references": ["doc-2", "doc-1"],
                "confidence": 0.91,
            },
        ]

    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
        return self.responses.pop(0)


def _seed_memory(container, session_id: str):
    asyncio.run(
        container.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.user,
                content="Tell me about Qinglan steam mop.",
            )
        )
    )
    asyncio.run(
        container.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.assistant,
                content="It is a steam mop product for home cleaning.",
            )
        )
    )


def _extract_final_payload(sse_text: str) -> dict:
    current_event = None
    for line in sse_text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
            continue
        if current_event == "final" and line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError("final SSE event not found")


def test_chat_stream_runs_real_qa_agent_chain(client, auth_headers):
    session_id = "qa-api-session"
    container = client.app.state.container

    _seed_memory(container, session_id)

    pipeline = StubPipeline()
    container.graph_runtime.router_agent = StubRouterAgent()
    container.graph_runtime.qa_agent = QAAgent(
        retrieval_pipeline=pipeline,
        llm_client=StubLLM(),
    )

    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "user_input": "What is the difference from a normal mop?",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
    )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: final" in response.text
    assert "steam cleaning is stronger than a normal mop" in response.text
    assert pipeline.last_query == "What is the difference between Qinglan steam mop and a normal mop?"
    assert pipeline.last_source_hint == "product_detail"

    final_payload = _extract_final_payload(response.text)
    assert final_payload["intent"] == "qa"
    assert final_payload["guardrail_pass"] is True
    assert final_payload["message"]["metadata"]["rewritten_query"] == pipeline.last_query
    assert final_payload["message"]["metadata"]["qa_confidence"] == 0.91
    assert final_payload["message"]["metadata"]["references"] == ["doc-2", "doc-1"]
    assert final_payload["message"]["metadata"]["unresolved"] is False

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages", headers=auth_headers)
    assert messages_response.status_code == 200
    messages = messages_response.json()["data"]
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert assistant_messages[-1]["metadata"]["rewritten_query"] == pipeline.last_query


def test_chat_stream_routes_noise_query_to_direct_reply(client, auth_headers):
    session_id = "direct-api-session"

    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "user_input": "1111",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
    )

    assert response.status_code == 200
    final_payload = _extract_final_payload(response.text)
    assert final_payload["intent"] == "unknown"
    assert final_payload["message"]["agent_name"] == "direct"
    assert final_payload["message"]["metadata"]["route_target"] == "direct"
    assert final_payload["message"]["metadata"]["requires_retrieval"] is False
    assert final_payload["message"]["metadata"]["references"] == []


def test_chat_stream_can_recall_last_user_question_from_short_term_memory(client, auth_headers):
    session_id = "qa-memory-api-session"
    container = client.app.state.container

    _seed_memory(container, session_id)
    container.graph_runtime.router_agent = StubMemoryRouterAgent()

    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "user_input": "刚刚我问你的是什么问题？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
    )

    assert response.status_code == 200
    final_payload = _extract_final_payload(response.text)
    assert final_payload["intent"] == "qa"
    assert final_payload["message"]["agent_name"] == "qa"
    assert final_payload["message"]["content"] == "你刚刚问的是：“Tell me about Qinglan steam mop.”。"
    assert final_payload["message"]["metadata"]["references"] == []
