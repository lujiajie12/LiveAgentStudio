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
    fallback_reason: str | None = None
    low_confidence: bool = False


class RouterAgent(BaseAgent):
    name = "router"

    def __init__(self, llm_gateway: LLMGateway):
        self.llm_gateway = llm_gateway

    def _build_prompts(self, state: LiveAgentState) -> tuple[str, str]:
        system_prompt = (
            "你是直播运营 AI 系统的 Router Agent，只负责意图分类。"
            "请输出纯 JSON，格式为 "
            '{"intent":"qa|script|analyst|unknown","confidence":0.0,"reason":"..."}。'
            "不要输出 markdown，不要输出额外解释。"
        )
        user_prompt = json.dumps(
            {
                "user_input": state["user_input"],
                "live_stage": state.get("live_stage"),
                "current_product_id": state.get("current_product_id"),
                "intent_definitions": {
                    "qa": "客观商品、规则、售后问答",
                    "script": "主播话术、促单、互动引导",
                    "analyst": "复盘、统计、报告",
                    "unknown": "无关直播或无法归类",
                },
                "few_shots": [
                    {"input": "这个面膜适合敏感肌吗", "intent": "qa"},
                    {"input": "帮我说一下这款产品卖点", "intent": "script"},
                    {"input": "今天直播里问最多的是什么", "intent": "analyst"},
                    {"input": "今天天气怎么样", "intent": "unknown"},
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
            )
        except TimeoutError:
            fallback_reason = "timeout"
            decision = RouterDecision(
                intent=IntentType.qa,
                confidence=0.0,
                reason="timeout fallback to qa",
                fallback_reason=fallback_reason,
            )
        except Exception:
            fallback_reason = "parse_error"
            decision = RouterDecision(
                intent=IntentType.qa,
                confidence=0.0,
                reason="parse fallback to qa",
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
            "route_fallback_reason": decision.fallback_reason,
            "route_low_confidence": decision.low_confidence,
            "agent_name": self.name,
        }
