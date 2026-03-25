import pytest

from app.agents.qa_agent import QAAgent, QA_LOW_CONFIDENCE_TEXT, QA_NO_ANSWER_TEXT


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
