import json
import time

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.graph.state import LiveAgentState, StatePatch
from app.schemas.domain import IntentType
from app.services.llm_gateway import LLMGateway

logger = get_logger(__name__)


class RouterDecision(BaseModel):
    intent: IntentType
    confidence: float
    reason: str
    knowledge_scope: str = "mixed"
    fallback_reason: str | None = None
    low_confidence: bool = False


class RouterAgent(BaseAgent):
    name = "router"

    def __init__(self, llm_gateway: LLMGateway):
        self.llm_gateway = llm_gateway

    def _build_prompts(self, state: LiveAgentState) -> tuple[str, str]:
        system_prompt = (
            "你是直播电商系统的 Router Agent，只做分类，不做回答。"
            "你必须输出单行 JSON，不要输出 markdown，不要输出额外解释。"
            '输出格式固定为{"intent":"qa|script|analyst|unknown","confidence":0.0,'
            '"knowledge_scope":"product_detail|faq|mixed","reason":"简短原因"}。'
            "分类规则："
            "qa=用户在问客观事实，如商品价格、规格参数、技术信息、产品细节、适用人群、商品对比、活动规则、发货、物流、售后、保修、退换。"
            "script=用户要求生成主播口播、促单话术、卖点包装、互动引导、直播表达。"
            "analyst=用户要求复盘、统计、总结、高频问题、表现分析、报告。"
            "unknown=与直播业务无关。"
            "knowledge_scope 只表示 qa 或检索时应优先参考哪类资料："
            "product_detail=商品详情/参数/卖点/对比/适用场景；"
            "faq=常见问答/规则/物流/售后/使用说明；"
            "mixed=两个资料库都可能需要。"
            "如果用户在问“适合什么人/什么场景”“和别的产品有什么区别”“功率/容量/价格/材质/参数”等，即使语气口语化，也应判为 qa，且 knowledge_scope 优先 product_detail。"
        )
        user_prompt = json.dumps(
            {
                "user_input": state["user_input"],
                "live_stage": state.get("live_stage"),
                "current_product_id": state.get("current_product_id"),
                "few_shots": [
                    {
                        "input": "青岚超净蒸汽拖洗一体机适合什么家庭用？跟普通拖把的区别是什么？",
                        "intent": "qa",
                        "knowledge_scope": "product_detail",
                    },
                    {
                        "input": "这款拖洗机下单后多久发货，坏了怎么保修？",
                        "intent": "qa",
                        "knowledge_scope": "faq",
                    },
                    {
                        "input": "帮我写一段这款拖洗机的直播口播，重点突出去污和省时",
                        "intent": "script",
                        "knowledge_scope": "product_detail",
                    },
                    {
                        "input": "今天直播里用户最关心这款拖洗机的哪些问题？",
                        "intent": "analyst",
                        "knowledge_scope": "mixed",
                    },
                    {
                        "input": "今天天气怎么样",
                        "intent": "unknown",
                        "knowledge_scope": "mixed",
                    },
                ],
            },
            ensure_ascii=False,
        )
        return system_prompt, user_prompt

    async def run(self, state: LiveAgentState) -> StatePatch:
        start = time.perf_counter()
        system_prompt, user_prompt = self._build_prompts(state)
        fallback_reason = None

        try:
            raw = await self.llm_gateway.ainvoke_json(system_prompt, user_prompt)
            decision = RouterDecision(
                intent=IntentType(raw["intent"]),
                confidence=float(raw["confidence"]),
                reason=str(raw.get("reason", "")),
                knowledge_scope=str(raw.get("knowledge_scope", "mixed")),
            )
        except TimeoutError:
            fallback_reason = "timeout"
            decision = RouterDecision(
                intent=IntentType.qa,
                confidence=0.0,
                reason="timeout fallback to qa",
                knowledge_scope="mixed",
                fallback_reason=fallback_reason,
            )
        except Exception:
            fallback_reason = "parse_error"
            decision = RouterDecision(
                intent=IntentType.qa,
                confidence=0.0,
                reason="parse fallback to qa",
                knowledge_scope="mixed",
                fallback_reason=fallback_reason,
            )

        if decision.confidence < settings.ROUTER_CONFIDENCE_THRESHOLD:
            decision.low_confidence = True
            if decision.intent == IntentType.unknown:
                decision.fallback_reason = decision.fallback_reason or "low_confidence_unknown"
            else:
                decision.intent = IntentType.qa
                decision.fallback_reason = decision.fallback_reason or "low_confidence"

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "router_decision trace_id=%s intent=%s confidence=%.2f duration_ms=%s fallback_reason=%s",
            state.get("trace_id"),
            decision.intent.value,
            decision.confidence,
            duration_ms,
            decision.fallback_reason,
        )
        return {
            "intent": decision.intent.value,
            "intent_confidence": decision.confidence,
            "route_reason": decision.reason,
            "knowledge_scope": decision.knowledge_scope,
            "route_fallback_reason": decision.fallback_reason,
            "route_low_confidence": decision.low_confidence,
            "agent_name": self.name,
        }
