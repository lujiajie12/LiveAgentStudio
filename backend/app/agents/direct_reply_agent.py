import json
import re
from typing import Protocol

from app.agents.base import BaseAgent
from app.graph.state import LiveAgentState, StatePatch


class DirectReplyLLM(Protocol):
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        ...


EXPLICIT_LIVE_CONTEXT_PATTERNS = (
    "今天这场直播主推什么",
    "这场直播主推什么",
    "当前直播主推什么",
    "现在主推什么",
    "今天主推什么",
    "当前讲什么商品",
    "当前讲解什么商品",
    "现在讲什么商品",
    "现在卖什么",
    "当前在播什么",
    "直播间现在卖什么",
    "直播间现在讲什么",
    "今天播什么",
    "当前商品是什么",
)

GREETING_PATTERNS = (
    "你好",
    "您好",
    "hi",
    "hello",
    "在吗",
)

LIVE_CONTEXT_LEAK_PATTERNS = (
    "直播间",
    "当前直播",
    "当前讲解",
    "当前商品",
    "主推",
    "SKU-",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _looks_like_noise_input(query: str) -> bool:
    compact = query.strip()
    if not compact:
        return True
    if re.fullmatch(r"[0-9\s]+", compact):
        return True
    if re.fullmatch(r"[0-9A-Za-z\W_]{1,3}", compact):
        return True
    if re.fullmatch(r"(.)\1{2,}", compact):
        return True
    return False


def _try_basic_math_answer(query: str) -> str | None:
    raw_query = query
    normalized = (
        query.replace("？", "")
        .replace("?", "")
        .replace("等于几", "")
        .replace("等于多少", "")
        .replace("等于", "")
        .replace("是多少", "")
        .replace("请问", "")
        .strip()
    )
    if not normalized:
        return None
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", normalized):
        return None
    if not any(operator in normalized for operator in ("+", "-", "*", "/", "(", ")")) and not any(
        hint in raw_query for hint in ("等于几", "等于多少", "是多少")
    ):
        return None
    try:
        value = eval(normalized, {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{normalized} = {value}。"


class DirectReplyAgent(BaseAgent):
    name = "direct"

    def __init__(self, llm_client: DirectReplyLLM | None = None):
        self.llm_client = llm_client

    def _should_include_live_context(self, query: str) -> bool:
        normalized = _normalize_text(query)
        return any(pattern in normalized for pattern in EXPLICIT_LIVE_CONTEXT_PATTERNS)

    def _is_greeting(self, query: str) -> bool:
        lowered = _normalize_text(query).lower()
        return any(pattern in lowered for pattern in GREETING_PATTERNS)

    def _has_live_context_leak(self, answer: str, current_product_id: str) -> bool:
        normalized = _normalize_text(answer)
        if current_product_id and current_product_id in normalized:
            return True
        return any(pattern in normalized for pattern in LIVE_CONTEXT_LEAK_PATTERNS)

    def _fallback_reply(self, state: LiveAgentState) -> str:
        query = _normalize_text(state.get("user_input", ""))
        current_product_id = _normalize_text(state.get("current_product_id"))

        math_answer = _try_basic_math_answer(query)
        if math_answer:
            return math_answer

        if self._is_greeting(query):
            return "你好，我在。你可以直接问我商品参数、运费、发货、售后，或者让我生成直播话术。"

        if _looks_like_noise_input(query):
            return "这个输入还不够明确。请直接告诉我你要处理的问题，比如“运费谁出”或“这款适合什么家庭使用”。"

        if self._should_include_live_context(query):
            if current_product_id:
                return f"当前直播间正在讲解 {current_product_id}。如果你想了解卖点、参数、售后或物流，我可以继续补充。"
            return "当前还没有接入直播商品信息，所以我暂时无法判断现在正在讲哪款商品。你可以先同步直播房间状态，或者直接告诉我商品名称。"

        return "这是一个不需要知识库检索的简单问题。我可以直接回答；如果你想问商品参数、售后、物流、适用场景或对比信息，我再调用知识库来处理。"

    async def run(self, state: LiveAgentState) -> StatePatch:
        query = _normalize_text(state.get("user_input", ""))
        current_product_id = _normalize_text(state.get("current_product_id"))
        include_live_context = self._should_include_live_context(query)

        if include_live_context and not current_product_id:
            return {
                "agent_output": "当前还没有接入直播商品信息，所以我暂时无法判断现在正在讲哪款商品。你可以先同步直播房间状态，或者直接告诉我商品名称。",
                "references": [],
                "retrieved_docs": [],
                "qa_confidence": 0.0,
                "unresolved": False,
                "agent_name": self.name,
            }

        if self.llm_client is None:
            answer = self._fallback_reply(state)
            return {
                "agent_output": answer,
                "references": [],
                "retrieved_docs": [],
                "qa_confidence": 0.0,
                "unresolved": False,
                "agent_name": self.name,
            }

        system_prompt = (
            "你是直播电商中台的快速直答助手。\n"
            "你的任务是处理不需要知识库检索的简单问题、常识问题、打招呼、测试输入和直播上下文确认问题。\n"
            "只有当用户明确在问“当前直播主推什么/现在讲什么商品/当前在播什么”这类直播上下文问题时，"
            "你才可以参考提供的直播商品、直播阶段和直播快照。\n"
            "如果问题是数学题、常识题、打招呼、测试输入或与直播商品无关的问题，必须直接就问题回答，"
            "绝不要主动提直播商品、SKU、直播阶段、优惠或当前主推内容。\n"
            "如果用户问的是当前直播商品，但系统没有提供 current_product_id，必须诚实说明“当前还没有接入直播商品信息”。\n"
            "如果输入无意义或不明确，请礼貌要求补充，不要编造。\n"
            "回答控制在 1 到 3 句，中文自然简洁。"
        )
        user_prompt = json.dumps(
            {
                "user_input": query,
                "include_live_context": include_live_context,
                "current_product_id": current_product_id if include_live_context else None,
                "live_stage": state.get("live_stage") if include_live_context else None,
                "live_offer_snapshot": state.get("live_offer_snapshot", {}) if include_live_context else {},
                "short_term_memory": list(state.get("short_term_memory", []))[-4:] if include_live_context else [],
                "route_reason": state.get("route_reason"),
                "route_fallback_reason": state.get("route_fallback_reason"),
            },
            ensure_ascii=False,
        )

        try:
            answer = (await self.llm_client.ainvoke_text(system_prompt, user_prompt)).strip()
        except Exception:
            answer = self._fallback_reply(state)

        if not answer:
            answer = self._fallback_reply(state)

        if not include_live_context and self._has_live_context_leak(answer, current_product_id):
            answer = self._fallback_reply(state)

        return {
            "agent_output": answer,
            "references": [],
            "retrieved_docs": [],
            "qa_confidence": 0.0,
            "unresolved": False,
            "agent_name": self.name,
        }
