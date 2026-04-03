import pytest

from app.agents.qa_agent import QAAgent, QA_LOW_CONFIDENCE_TEXT, QA_NO_ANSWER_TEXT
from app.core.config import settings
from app.memory.memory_service import MemoryRecord


class StubPipeline:
    def __init__(self, results=None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.last_query = None
        self.last_source_hint = None

    async def retrieve(self, query: str, source_hint: str | None = None):
        self.last_query = query
        self.last_source_hint = source_hint
        if self.error:
            raise self.error
        return "context", self.results


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
    def __init__(self, json_responses=None, text_responses=None):
        self.json_responses = list(json_responses or [])
        self.text_responses = list(text_responses or [])
        self.calls = []

    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        self.calls.append(("json", system_prompt, user_prompt))
        if not self.json_responses:
            raise RuntimeError("no json response")
        response = self.json_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def ainvoke_text(self, system_prompt: str, user_prompt: str):
        self.calls.append(("text", system_prompt, user_prompt))
        if not self.text_responses:
            raise RuntimeError("no text response")
        response = self.text_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class StubSearchClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[str] = []

    async def search(self, query: str) -> dict:
        self.calls.append(query)
        return self.payload


class StubMemoryHook:
    def __init__(self, search_results=None, recent_results=None):
        self.search_results = list(search_results or [])
        self.recent_results = list(recent_results or [])

    async def search_for_state(self, state):
        _ = state
        return list(self.search_results)

    async def list_recent_for_state(self, state, limit: int = 3):
        _ = state
        return list(self.recent_results[:limit])

    def serialize_memories(self, memories):
        return [
            {
                "memory_id": item.memory_id,
                "memory": item.memory,
                "score": item.score,
                "metadata": item.metadata,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in memories
        ]

    def build_prompt_context(self, memories):
        return "\n".join(item.memory for item in memories)


def make_state(user_input: str = "What kind of family is this product suitable for?") -> dict:
    return {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "user_input": user_input,
        "live_stage": "pitch",
        "current_product_id": "SKU-1",
        "short_term_memory": [
            {"role": "user", "content": "Tell me about Qinglan steam mop."},
            {"role": "assistant", "content": "It focuses on steam cleaning and mop-vacuum integration."},
        ],
        "knowledge_scope": "product_detail",
    }


def make_results() -> list[StubResult]:
    return [
        StubResult("doc-1", "Suitable for families with children or pets.", metadata={"source_file": "product_detail.md"}),
        StubResult("doc-2", "Compared with a normal mop, steam cleaning removes stains faster.", metadata={"source_file": "product_detail.md"}),
        StubResult("doc-3", "Water tank is 650ml and cable length is 6m.", metadata={"source_file": "product_detail.md"}),
    ]


@pytest.mark.asyncio
async def test_qa_agent_uses_rewritten_query_and_returns_structured_answer():
    pipeline = StubPipeline(results=make_results())
    llm = StubLLM(
        json_responses=[
            {"rewritten_query": "What is the difference between Qinglan steam mop and a normal mop?"},
            {
                "answer": "It is more suitable for families with children or pets, and steam cleaning is stronger than a normal mop.",
                "references": ["doc-2", "doc-1"],
                "confidence": 0.88,
            },
        ]
    )
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    result = await agent.run(make_state("What is the difference from a normal mop?"))

    assert pipeline.last_query == "What is the difference between Qinglan steam mop and a normal mop?"
    assert pipeline.last_source_hint == "product_detail"
    assert result["rewritten_query"] == "What is the difference between Qinglan steam mop and a normal mop?"
    assert result["agent_output"].startswith("It is more suitable")
    assert result["references"] == ["doc-2", "doc-1"]
    assert len(result["retrieved_docs"]) == 3
    assert result["qa_confidence"] == 0.88
    assert result["unresolved"] is False


@pytest.mark.asyncio
async def test_qa_agent_normalizes_rewritten_query_spacing():
    pipeline = StubPipeline(results=make_results())
    llm = StubLLM(
        json_responses=[
            {"rewritten_query": "青岚超净蒸汽拖洗一体机适合什么家庭 用？ 跟普通拖把的区别 是什么？"},
            {
                "answer": "适合有孩子或养宠家庭，蒸汽去污能力强于普通拖把。",
                "references": ["doc-1", "doc-2"],
                "confidence": 0.9,
            },
        ]
    )
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    result = await agent.run(make_state("这款适合什么家庭用？跟普通拖把的区别是什么？"))

    assert result["rewritten_query"] == "青岚超净蒸汽拖洗一体机适合什么家庭用？跟普通拖把的区别是什么？"
    assert pipeline.last_query == result["rewritten_query"]


@pytest.mark.asyncio
async def test_qa_agent_uses_text_fallback_when_json_generation_fails():
    pipeline = StubPipeline(results=make_results())
    llm = StubLLM(
        json_responses=[
            {"rewritten_query": "What is the difference between Qinglan steam mop and a normal mop?"},
            ValueError("bad json"),
        ],
        text_responses=[
            "It suits families with children or pets, and steam cleaning is stronger than a normal mop.",
        ],
    )
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    result = await agent.run(make_state("What is the difference from a normal mop?"))

    assert result["agent_output"].startswith("It suits families")
    assert result["references"] == ["doc-1", "doc-2", "doc-3"]
    assert result["qa_confidence"] == 0.68
    assert result["unresolved"] is False


@pytest.mark.asyncio
async def test_qa_agent_returns_zero_retrieval_fallback():
    pipeline = StubPipeline(results=[])
    llm = StubLLM(json_responses=[{"rewritten_query": "How long is the warranty?"}])
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    result = await agent.run(make_state("How long is the warranty?"))

    assert result["agent_output"] == QA_NO_ANSWER_TEXT
    assert result["references"] == []
    assert result["retrieved_docs"] == []
    assert result["qa_confidence"] == 0.0
    assert result["unresolved"] is True


@pytest.mark.asyncio
async def test_qa_agent_uses_current_datetime_tool_without_retrieval():
    agent = QAAgent(retrieval_pipeline=None, llm_client=StubLLM())

    result = await agent.run(
        make_state("今天是周几？")
        | {
            "current_product_id": None,
            "requires_retrieval": False,
            "tool_intent": "datetime",
        }
    )

    assert "今天是星期" in result["agent_output"]
    assert "当前时间是" in result["agent_output"]
    assert result["references"] == []
    assert result["retrieved_docs"] == []
    assert result["qa_confidence"] == 1.0
    assert result["unresolved"] is False
    assert result["tools_used"] == ["current_datetime"]
    assert "current_datetime" in result["tool_outputs"]


@pytest.mark.asyncio
async def test_qa_agent_uses_google_search_tool_without_retrieval(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test-serpapi-key")
    llm = StubLLM()
    agent = QAAgent(retrieval_pipeline=None, llm_client=llm)
    search_client = StubSearchClient(
        {
            "query": "今日黄金金价是多少？",
            "answer_box": {
                "title": "黄金金价",
                "answer": "今日黄金价格约为每克 728 元。",
                "link": "https://example.com/gold",
            },
            "knowledge_graph": {},
            "organic_results": [
                {
                    "title": "黄金价格",
                    "link": "https://example.com/gold",
                    "snippet": "今日黄金价格约为每克 728 元。",
                    "source": "Example Finance",
                    "position": 1,
                }
            ],
            "search_metadata": {"id": "search-1", "status": "Success"},
        }
    )
    agent.bind_web_search_client(search_client)

    result = await agent.run(
        make_state("今日黄金金价是多少？")
        | {
            "current_product_id": None,
            "requires_retrieval": False,
            "tool_intent": "web_search",
        }
    )
    assert search_client.calls == ["今日黄金金价是多少？"]
    assert result["agent_output"] == "今日黄金价格约为每克 728 元。"
    assert result["references"] == ["https://example.com/gold"]
    assert result["retrieved_docs"] == []
    assert result["qa_confidence"] == 0.84
    assert result["unresolved"] is False
    assert result["tools_used"] == ["google_search"]
    assert "google_search" in result["tool_outputs"]
    assert len(llm.calls) == 1
    assert llm.calls[0][0] == "json"


@pytest.mark.asyncio
async def test_qa_agent_reuses_preloaded_google_search_observation_without_duplicate_search(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test-serpapi-key")
    llm = StubLLM()
    agent = QAAgent(retrieval_pipeline=None, llm_client=llm)
    search_client = StubSearchClient(
        {
            "query": "今日黄金金价是多少？",
            "answer_box": {
                "title": "黄金金价",
                "answer": "今日黄金价格约为每克 728 元。",
                "link": "https://example.com/gold",
            },
            "knowledge_graph": {},
            "organic_results": [],
            "search_metadata": {"id": "search-1", "status": "Success"},
        }
    )
    agent.bind_web_search_client(search_client)

    result = await agent.run(
        make_state("今日黄金金价是多少？")
        | {
            "current_product_id": None,
            "requires_retrieval": False,
            "tool_intent": "web_search",
            "rewritten_query": "今日黄金金价是多少？",
            "tool_outputs": {
                "google_search": {
                    "query": "今日黄金金价是多少？",
                    "answer_box": {
                        "title": "黄金金价",
                        "answer": "今日黄金价格约为每克 728 元。",
                        "link": "https://example.com/gold",
                    },
                    "knowledge_graph": {},
                    "organic_results": [],
                    "search_metadata": {"id": "search-1", "status": "Success"},
                }
            },
        }
    )

    assert search_client.calls == []
    assert llm.calls == []
    assert result["agent_output"] == "今日黄金价格约为每克 728 元。"
    assert result["references"] == ["https://example.com/gold"]
    assert result["tools_used"] == ["google_search"]
    assert result["tool_outputs"]["google_search"]["query"] == "今日黄金金价是多少？"


@pytest.mark.asyncio
async def test_qa_agent_downgrades_low_confidence_answers():
    pipeline = StubPipeline(
        results=[StubResult("doc-1", "Warranty is one year.", metadata={"source_file": "FAQ.xlsx"}, source_type="faq")]
    )
    llm = StubLLM(
        json_responses=[
            {"rewritten_query": "How long is the warranty?"},
            {"answer": "Warranty is one year.", "references": ["doc-1"], "confidence": 0.2},
        ]
    )
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    result = await agent.run(make_state("How long is the warranty?"))

    assert result["agent_output"] == QA_LOW_CONFIDENCE_TEXT
    assert result["references"] == ["doc-1"]
    assert result["qa_confidence"] == 0.2
    assert result["unresolved"] is True


@pytest.mark.asyncio
async def test_qa_agent_recalls_last_user_question_from_short_term_memory():
    pipeline = StubPipeline(results=make_results())
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=StubLLM())

    result = await agent.run(make_state("刚刚我问你的是什么问题？") | {"tool_intent": "memory_recall"})

    assert result["agent_output"] == "你刚刚问的是：“Tell me about Qinglan steam mop.”。"
    assert result["retrieved_docs"] == []
    assert pipeline.last_query is None
    assert result["qa_confidence"] == 0.99
    assert result["unresolved"] is False


@pytest.mark.asyncio
async def test_qa_agent_can_recall_recent_user_questions_list_via_llm_memory_plan():
    pipeline = StubPipeline(results=make_results())
    llm = StubLLM(
        json_responses=[
            {"focus": "question", "mode": "list", "limit": 3, "reason": "user asks for several recent questions"},
            {
                "answer": "你刚刚问过的 3 个问题是：\n1. 第一个问题是什么？\n2. 第二个问题是什么？\n3. 第三个问题是什么？",
                "confidence": 0.93,
                "unresolved": False,
            },
        ]
    )
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=llm)

    state = make_state("我刚刚问的几个问题是什么？") | {"tool_intent": "memory_recall"}
    state["short_term_memory"] = [
        {"role": "user", "content": "第一个问题是什么？"},
        {"role": "assistant", "content": "第一个回答。"},
        {"role": "user", "content": "第二个问题是什么？"},
        {"role": "assistant", "content": "第二个回答。"},
        {"role": "user", "content": "第三个问题是什么？"},
        {"role": "assistant", "content": "第三个回答。"},
    ]

    result = await agent.run(state)

    assert result["agent_output"] == (
        "你刚刚问过的 3 个问题是：\n1. 第一个问题是什么？\n2. 第二个问题是什么？\n3. 第三个问题是什么？"
    )
    assert result["qa_confidence"] == 0.93
    assert result["unresolved"] is False
    assert len(llm.calls) == 2
    assert llm.calls[0][0] == "json"
    assert llm.calls[1][0] == "json"


@pytest.mark.asyncio
async def test_qa_agent_recalls_last_assistant_answer_from_short_term_memory():
    pipeline = StubPipeline(results=make_results())
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=StubLLM())

    result = await agent.run(make_state("你刚刚是怎么回答的？") | {"tool_intent": "memory_recall"})

    assert result["agent_output"] == (
        "我上一轮的回答是：“It focuses on steam cleaning and mop-vacuum integration.”。"
    )
    assert result["retrieved_docs"] == []
    assert pipeline.last_query is None
    assert result["qa_confidence"] == 0.99
    assert result["unresolved"] is False


@pytest.mark.asyncio
async def test_qa_agent_falls_back_to_long_term_memory_for_recall_queries():
    pipeline = StubPipeline(results=make_results())
    agent = QAAgent(retrieval_pipeline=pipeline, llm_client=StubLLM())
    agent.bind_memory_hook(
        StubMemoryHook(
            recent_results=[
                MemoryRecord(
                    memory_id="memory-1",
                    memory="用户之前问过青岚蒸汽拖洗一体机适合什么家庭使用。",
                    score=0.82,
                    metadata={"memory_summary": "用户之前问过青岚蒸汽拖洗一体机适合什么家庭使用。"},
                    created_at="2026-04-01T10:00:00Z",
                    updated_at="2026-04-01T10:00:00Z",
                )
            ]
        )
    )

    state = make_state("你还记得我之前问过什么吗？")
    state["short_term_memory"] = []
    state["tool_intent"] = "memory_recall"
    result = await agent.run(state)

    assert "长期记忆里找到最近与你相关的内容" in result["agent_output"]
    assert "用户之前问过青岚蒸汽拖洗一体机适合什么家庭使用。" in result["agent_output"]
    assert result["retrieved_docs"] == []
    assert pipeline.last_query is None
    assert result["long_term_memory_hits"] == 1
    assert result["unresolved"] is False
