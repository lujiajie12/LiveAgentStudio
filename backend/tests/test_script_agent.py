import json

import pytest

from app.agents.script_agent import ScriptAgent


class StubResult:
    def __init__(self, doc_id: str, content: str, final_score: float = 0.9, source_type: str = "product_detail"):
        self.doc_id = doc_id
        self.content = content
        self.final_score = final_score
        self.source_type = source_type
        self.metadata = {"source_file": "product_detail.md"}


class StubPipeline:
    def __init__(self):
        self.last_query = None
        self.last_source_hint = None

    async def retrieve(self, query: str, source_hint: str | None = None):
        self.last_query = query
        self.last_source_hint = source_hint
        return "context", [
            StubResult("doc-1", "适合有孩子和养宠家庭，主打蒸汽高温去污与拖吸一体。"),
            StubResult("doc-2", "当前直播讲解重点是清洁效率、适用地面和核心参数。"),
        ]


class StubLLM:
    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        _ = system_prompt, user_prompt
        return {
            "script_type": "promotion",
            "tone": "promotional",
            "reason": "当前需求明显带有促单目标。",
            "content": "家人们，这款现在很适合趁活动节奏直接下单。",
            "candidates": [
                "家人们，这款现在很适合趁活动节奏直接下单。",
                "喜欢这种高效清洁体验的宝宝，现在可以直接拍。",
                "这一轮价格和节奏都很合适，想要的现在别再等了。",
            ],
        }


class SpyLLM:
    def __init__(self):
        self.system_prompt = ""
        self.user_prompt = ""

    async def ainvoke_json(self, system_prompt: str, user_prompt: str):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {
            "script_type": "promotion",
            "tone": "promotional",
            "reason": "基于实时快照和商品素材生成促单话术。",
            "content": "家人们，当前页面库存和优惠信息都很适合直接转化。",
            "candidates": [
                "家人们，当前页面库存和优惠信息都很适合直接转化。",
            ],
        }


@pytest.mark.asyncio
async def test_script_agent_generates_candidates_and_metadata():
    pipeline = StubPipeline()
    agent = ScriptAgent(retrieval_pipeline=pipeline, llm_client=StubLLM())

    result = await agent.run(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "user_input": "帮我来一段促单话术，强调这款清洁工具值得现在下单。",
            "live_stage": "closing",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
            "hot_keywords": [],
            "script_style": None,
            "live_offer_snapshot": {},
        }
    )

    assert pipeline.last_source_hint == "mixed"
    assert result["script_type"] == "promotion"
    assert result["script_tone"] == "promotional"
    assert result["script_reason"] == "当前需求明显带有促单目标。"
    assert len(result["script_candidates"]) == 3
    assert "方案1：" in result["agent_output"]
    assert result["references"] == ["doc-1", "doc-2"]


@pytest.mark.asyncio
async def test_script_agent_prioritizes_explicit_promotion_over_hot_topic():
    pipeline = StubPipeline()
    agent = ScriptAgent(retrieval_pipeline=pipeline, llm_client=StubLLM())

    result = await agent.run(
        {
            "trace_id": "trace-2",
            "session_id": "session-2",
            "user_id": "user-1",
            "user_input": "帮我来一段促单话术，强调库存快没了。",
            "live_stage": "closing",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
            "hot_keywords": ["库存", "优惠"],
            "script_style": "促销型",
            "live_offer_snapshot": {},
        }
    )

    assert result["script_type"] == "promotion"


@pytest.mark.asyncio
async def test_script_agent_injects_live_offer_snapshot_and_chinese_rules():
    pipeline = StubPipeline()
    llm = SpyLLM()
    agent = ScriptAgent(retrieval_pipeline=pipeline, llm_client=llm)

    await agent.run(
        {
            "trace_id": "trace-3",
            "session_id": "session-3",
            "user_id": "user-1",
            "user_input": "帮我来一段促单话术，结合库存和当前活动节奏。",
            "live_stage": "closing",
            "current_product_id": "SKU-1",
            "short_term_memory": [],
            "hot_keywords": ["库存", "优惠", "限时"],
            "script_style": "促销型",
            "live_offer_snapshot": {
                "display_stock": 92,
                "display_unit": "套",
                "current_price": "89元",
                "original_price": "149元",
                "countdown_seconds": 180,
                "coupon_summary": "下单立减20元",
                "gift_summary": "赠清洁布1份",
                "ignored_field": "should_be_removed",
            },
        }
    )

    assert "动态事实只能来自 live_offer_snapshot" in llm.system_prompt

    payload = json.loads(llm.user_prompt)
    assert payload["live_offer_snapshot"] == {
        "display_stock": 92,
        "display_unit": "套",
        "current_price": "89元",
        "original_price": "149元",
        "countdown_seconds": 180,
        "coupon_summary": "下单立减20元",
        "gift_summary": "赠清洁布1份",
    }
    assert any("92套" in rule for rule in payload["dynamic_fact_rules"])
    assert any("180" in rule and "秒" in rule for rule in payload["dynamic_fact_rules"])
    assert any("89元" in rule for rule in payload["dynamic_fact_rules"])
