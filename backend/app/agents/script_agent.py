import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.qa_agent import ChatOpenAIJsonClient
from app.graph.state import LiveAgentState, StatePatch


SCRIPT_FALLBACK_TEXT = "这段时间可以先围绕核心卖点、适用场景和当前活动信息来组织口播。"


class ScriptAgent(BaseAgent):
    name = "script"

    # 初始化话术智能体，注入检索管线和 LLM 客户端。
    def __init__(self, retrieval_pipeline=None, llm_client: ChatOpenAIJsonClient | None = None):
        self.pipeline = retrieval_pipeline
        self.llm_client = llm_client or ChatOpenAIJsonClient()

    # 执行完整话术生成链路：识别场景、拉取素材、约束动态事实并生成可口播话术。
    # script_type 和 script_tone 由 Router LLM 预决策，直接从 state 读取。
    async def run(self, state: LiveAgentState) -> StatePatch:
        script_type = str(state.get("script_type") or "product_pitch").strip()
        script_tone = str(state.get("script_tone") or "friendly").strip()
        source_hint = self._resolve_source_hint(script_type, state)
        query = self._build_material_query(state, script_type)
        retrieved_docs = await self._retrieve_docs(query, source_hint)
        references = [doc["doc_id"] for doc in retrieved_docs]
        live_offer_snapshot = self._sanitize_live_offer_snapshot(state.get("live_offer_snapshot", {}))

        generated = await self._generate_script(
            state=state,
            script_type=script_type,
            script_tone=script_tone,
            retrieved_docs=retrieved_docs,
            live_offer_snapshot=live_offer_snapshot,
        )

        candidates = self._normalize_candidates(generated.get("candidates", []))
        content = self._normalize_script_text(str(generated.get("content", "")).strip())
        if not content and candidates:
            content = candidates[0]
        if not content:
            content = self._fallback_script(script_type, retrieved_docs, live_offer_snapshot)
            if not candidates:
                candidates = [content]

        return {
            "agent_output": self._render_output(content, candidates),
            "references": references,
            "retrieved_docs": retrieved_docs,
            "script_type": script_type,
            "script_tone": str(generated.get("tone", "") or script_tone),
            "script_reason": str(generated.get("reason", "") or self._default_reason(script_type)),
            "script_candidates": candidates,
            "agent_name": self.name,
        }

    # 根据输入语义和热词判断当前需要生成的话术类型。
    def _infer_script_type(self, state: LiveAgentState) -> str:
        query = str(state.get("user_input", "")).lower()
        hot_keywords = [str(item).strip().lower() for item in state.get("hot_keywords", []) if str(item).strip()]

        if any(token in query for token in ("促单", "库存", "抓紧", "最后", "限时", "涨回", "赶紧拍", "拍它")):
            return "promotion"
        if any(token in query for token in ("优惠", "券", "赠品", "满减", "福利", "立减")):
            return "benefit_reminder"
        if any(token in query for token in ("互动", "扣", "留人", "冷场", "评论区", "弹幕互动", "城市")):
            return "engagement"
        if hot_keywords and (
            any(keyword in query for keyword in hot_keywords)
            or any(token in query for token in ("弹幕", "好多宝宝问", "大家都在问"))
        ):
            return "hot_topic"
        return "product_pitch"

    # 结合显式风格配置和直播阶段推断更合适的话术语气。
    def _infer_tone(self, state: LiveAgentState, script_type: str) -> str:
        style = str(state.get("script_style", "") or "").strip().lower()
        if style in {"专业型", "professional"}:
            return "professional"
        if style in {"亲切型", "friendly"}:
            return "friendly"
        if style in {"促销型", "promotional"}:
            return "promotional"
        if script_type == "promotion" or state.get("live_stage") == "closing":
            return "promotional"
        query = str(state.get("user_input", ""))
        if any(token in query for token in ("参数", "规格", "成分", "技术", "功率", "容量")):
            return "professional"
        return "friendly"

    # 为不同话术类型选择更偏向的知识来源，减少无关素材噪声。
    def _resolve_source_hint(self, script_type: str, state: LiveAgentState) -> str:
        if script_type == "product_pitch":
            return "product_detail"
        if script_type == "benefit_reminder":
            return "faq"
        if script_type == "hot_topic":
            return str(state.get("knowledge_scope", "mixed") or "mixed")
        return "mixed"

    # 组装素材查询，在热点场景下把热词拼进检索语句里。
    def _build_material_query(self, state: LiveAgentState, script_type: str) -> str:
        query = str(state.get("user_input", "")).strip()
        hot_keywords = [str(item).strip() for item in state.get("hot_keywords", []) if str(item).strip()]
        if script_type == "hot_topic" and hot_keywords:
            return f"{query}；热点关键词：{'、'.join(hot_keywords[:5])}"
        return query

    # 调用混合检索获取可用于话术生成的候选素材片段。
    async def _retrieve_docs(self, query: str, source_hint: str) -> list[dict[str, Any]]:
        if self.pipeline is None:
            return []
        normalized_query = query
        if hasattr(self.pipeline, "normalize_query_semantics"):
            try:
                semantic_plan = await self.pipeline.normalize_query_semantics(query)
                normalized_query = str((semantic_plan or {}).get("normalized_query") or query).strip() or query
            except Exception:
                normalized_query = query
        try:
            _, rerank_results = await self.pipeline.retrieve(normalized_query, source_hint=source_hint)
        except Exception:
            return []

        docs: list[dict[str, Any]] = []
        for rank, result in enumerate(rerank_results[:4], start=1):
            metadata = dict(getattr(result, "metadata", {}) or {})
            docs.append(
                {
                    "rank": rank,
                    "doc_id": getattr(result, "doc_id", ""),
                    "content": getattr(result, "content", ""),
                    "score": getattr(result, "final_score", 0.0),
                    "source_type": getattr(result, "source_type", ""),
                    "metadata": metadata,
                }
            )
        return docs

    # 只保留可被话术提示词消费的实时快照字段，避免前端传入杂质结构。
    def _sanitize_live_offer_snapshot(self, snapshot: Any) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {}

        allowed_keys = {
            "display_stock",
            "display_unit",
            "stock_label",
            "is_stock_low",
            "current_price",
            "original_price",
            "discount_summary",
            "promo_end_at",
            "countdown_seconds",
            "gift_summary",
            "coupon_summary",
            "aftersales_summary",
            "activity_summary",
            "observed_at",
            "source",
        }
        sanitized: dict[str, Any] = {}
        for key in allowed_keys:
            value = snapshot.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                text = value.strip()
                if text:
                    sanitized[key] = text
                continue
            if isinstance(value, (int, float, bool)):
                sanitized[key] = value
                continue
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()]
                if items:
                    sanitized[key] = items
        return sanitized

    # 根据实时快照生成动态事实规则，明确哪些信息可以说，哪些不能编。
    def _build_dynamic_fact_rules(self, live_offer_snapshot: dict[str, Any]) -> list[str]:
        rules: list[str] = []
        unit = str(live_offer_snapshot.get("display_unit", "件") or "件")

        if "display_stock" in live_offer_snapshot:
            rules.append(f"库存：可使用精确口径“{live_offer_snapshot['display_stock']}{unit}”，不要擅自改成其他数字。")
        elif live_offer_snapshot.get("stock_label"):
            rules.append(f"库存：只能使用弱表述“{live_offer_snapshot['stock_label']}”，不要补充具体剩余数量。")
        elif live_offer_snapshot.get("is_stock_low") is True:
            rules.append("库存：仅可表达“库存紧张/数量有限”，禁止补充具体数量。")
        else:
            rules.append("库存：未提供实时口径，禁止说“仅剩xx件/套/单”等精确库存。")

        if "current_price" in live_offer_snapshot:
            if "original_price" in live_offer_snapshot:
                rules.append(
                    f"价格：可使用当前价 {live_offer_snapshot['current_price']} 和原价 {live_offer_snapshot['original_price']}，不要改写成其他价格。"
                )
            else:
                rules.append(f"价格：只可使用当前价 {live_offer_snapshot['current_price']}，不要补充原价或折扣差。")
        else:
            rules.append("价格：未提供实时价格，禁止口播具体价格、到手价或立减金额。")

        if "countdown_seconds" in live_offer_snapshot:
            rules.append(f"倒计时：可使用剩余 {live_offer_snapshot['countdown_seconds']} 秒，不要改成其他时长。")
        elif live_offer_snapshot.get("promo_end_at"):
            rules.append(f"倒计时：可使用活动截止时间 {live_offer_snapshot['promo_end_at']}，不要自行换算成其他分钟数。")
        else:
            rules.append("倒计时：未提供实时截止信息，禁止说“最后2分钟/马上结束/倒计时xx秒”等精确时长。")

        if live_offer_snapshot.get("gift_summary"):
            rules.append(f"赠品：仅可按“{live_offer_snapshot['gift_summary']}”描述，不要额外补充未给出的赠品。")
        else:
            rules.append("赠品：未提供赠品信息，禁止承诺“下单送xx”或“赠品全都有”。")

        if live_offer_snapshot.get("coupon_summary"):
            rules.append(f"优惠券：仅可按“{live_offer_snapshot['coupon_summary']}”描述，不要新增券额。")
        else:
            rules.append("优惠券：未提供优惠券信息，禁止承诺具体券额或满减门槛。")

        if live_offer_snapshot.get("aftersales_summary"):
            rules.append(f"售后：仅可按“{live_offer_snapshot['aftersales_summary']}”描述，不要新增售后承诺。")
        else:
            rules.append("售后：未提供实时售后活动规则，禁止额外承诺保价、赠保或特殊售后权益。")

        if live_offer_snapshot.get("activity_summary"):
            rules.append(f"活动摘要：可参考“{live_offer_snapshot['activity_summary']}”组织表达，但不得扩写未给出的活动细节。")

        return rules

    # 调用 LLM 生成结构化话术结果，并把静态素材与动态事实边界一并明确给模型。
    async def _generate_script(
        self,
        state: LiveAgentState,
        script_type: str,
        script_tone: str,
        retrieved_docs: list[dict[str, Any]],
        live_offer_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = (
            "你是直播运营系统中的话术生成智能体，只负责生成主播可直接口播的中文话术。\n"
            "你不是问答助手，不要回答用户知识问答，也不要解释推理过程。\n"
            "你必须严格遵守以下规则：\n"
            "1. 静态事实只能来自 knowledge_context，包括商品卖点、参数、适用场景、FAQ。\n"
            "2. 动态事实只能来自 live_offer_snapshot，包括库存、价格、优惠时间、赠品、优惠券、售后活动规则。\n"
            "3. 如果 live_offer_snapshot 没有某项字段，绝对不能编造该项的具体数字、价格、倒计时、赠品或售后承诺。\n"
            "4. 没有对应动态事实时，只能使用弱表述，例如“库存紧张”“优惠进行中”，且不要补充具体数值。\n"
            "5. 输出内容必须自然、简洁、可口播，语气要符合 tone 和直播阶段。\n"
            "6. 禁止输出 Markdown、额外解释、提示词复述。\n"
            '7. 只返回严格 JSON，格式为 {"script_type":"...","tone":"...","reason":"...","content":"...","candidates":["..."]}。'
        )
        candidate_count = 3 if script_type == "promotion" else 2
        user_prompt = json.dumps(
            {
                "user_input": state.get("user_input"),
                "live_stage": state.get("live_stage"),
                "current_product_id": state.get("current_product_id"),
                "hot_keywords": state.get("hot_keywords", []),
                "script_type": script_type,
                "tone": script_tone,
                "candidate_count": candidate_count,
                "knowledge_context": retrieved_docs,
                "live_offer_snapshot": live_offer_snapshot,
                "dynamic_fact_rules": self._build_dynamic_fact_rules(live_offer_snapshot),
            },
            ensure_ascii=False,
        )
        try:
            return await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            return {}

    # 对模型返回的候选话术做去重、文本清洗和数量裁剪。
    def _normalize_candidates(self, candidates: list[Any]) -> list[str]:
        normalized: list[str] = []
        for item in candidates or []:
            text = self._normalize_script_text(str(item).strip())
            if text and text not in normalized:
                normalized.append(text)
        return normalized[:3]

    # 统一清理模型输出里的异常空格，避免中文口播文本出现断裂。
    def _normalize_script_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。！？：；、“”‘’（）《》])", "", text)
        text = re.sub(r"(?<=[，。！？：；、“”‘’（）《》])\s+(?=[\u4e00-\u9fff])", "", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=\d)", "", text)
        text = re.sub(r"(?<=\d)\s+(?=[\u4e00-\u9fff])", "", text)
        return text.strip()

    # 当模型生成失败时，用检索素材和实时快照拼出保守且不编造的兜底话术。
    def _fallback_script(
        self,
        script_type: str,
        retrieved_docs: list[dict[str, Any]],
        live_offer_snapshot: dict[str, Any],
    ) -> str:
        if not retrieved_docs:
            dynamic_phrase = self._build_safe_dynamic_phrase(live_offer_snapshot, script_type)
            return dynamic_phrase or SCRIPT_FALLBACK_TEXT

        snippet = "；".join(
            doc["content"].strip()
            for doc in retrieved_docs[:2]
            if str(doc.get("content", "")).strip()
        )
        prefix_map = {
            "product_pitch": "这款产品当前最值得重点讲的是",
            "promotion": "这一轮促单可以重点强调",
            "benefit_reminder": "这一波福利提醒可以这样说",
            "engagement": "这段互动留存话术可以围绕",
            "hot_topic": "围绕当前高频关注点，可以直接这样接话",
        }
        prefix = prefix_map.get(script_type, "可以先围绕这些信息展开")
        dynamic_phrase = self._build_safe_dynamic_phrase(live_offer_snapshot, script_type)
        base = f"{prefix}：{snippet[:180]}"
        if dynamic_phrase:
            base = f"{base}；{dynamic_phrase}"
        return self._normalize_script_text(base)

    # 根据实时快照生成安全的动态补充短语，只引用已给出的实时口径。
    def _build_safe_dynamic_phrase(self, live_offer_snapshot: dict[str, Any], script_type: str) -> str:
        if script_type not in {"promotion", "benefit_reminder", "hot_topic"}:
            return ""

        phrases: list[str] = []
        unit = str(live_offer_snapshot.get("display_unit", "件") or "件")

        if "display_stock" in live_offer_snapshot:
            phrases.append(f"当前页面展示库存约为{live_offer_snapshot['display_stock']}{unit}")
        elif live_offer_snapshot.get("stock_label"):
            phrases.append(str(live_offer_snapshot["stock_label"]))
        elif live_offer_snapshot.get("is_stock_low") is True:
            phrases.append("当前库存偏紧")

        if "current_price" in live_offer_snapshot:
            phrases.append(f"当前页面价格可参考{live_offer_snapshot['current_price']}")
        if live_offer_snapshot.get("coupon_summary"):
            phrases.append(str(live_offer_snapshot["coupon_summary"]))
        if live_offer_snapshot.get("gift_summary"):
            phrases.append(str(live_offer_snapshot["gift_summary"]))
        if live_offer_snapshot.get("activity_summary"):
            phrases.append(str(live_offer_snapshot["activity_summary"]))

        return "，".join(phrases[:3])

    # 为每种话术类型提供默认的生成理由说明。
    def _default_reason(self, script_type: str) -> str:
        reason_map = {
            "product_pitch": "当前需求更适合突出商品卖点和适用场景。",
            "promotion": "当前需求带有明显促单和稀缺感表达诉求。",
            "benefit_reminder": "当前需求适合强调优惠、赠品或规则提醒。",
            "engagement": "当前需求更适合提升互动和留存。",
            "hot_topic": "当前需求与近期高频关注点重合，适合顺势引导。",
        }
        return reason_map.get(script_type, "根据当前场景生成对应直播话术。")

    # 把单条话术或多候选方案渲染成最终展示文本。
    def _render_output(self, content: str, candidates: list[str]) -> str:
        if len(candidates) <= 1:
            return content
        return "\n".join(f"方案{i}：{item}" for i, item in enumerate(candidates, start=1))
