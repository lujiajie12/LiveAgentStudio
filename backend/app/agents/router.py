import json
import re
import time
from typing import Any

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.graph.state import LiveAgentState, StatePatch
from app.schemas.domain import IntentType
from app.services.llm_gateway import LLMGateway

logger = get_logger(__name__)

NOISE_PATTERN = re.compile(r"^[0-9\W_]+$")
REPEATED_CHAR_PATTERN = re.compile(r"^(.)\1{2,}$")

SCRIPT_KEYWORDS = (
    "话术",
    "口播",
    "促单",
    "逼单",
    "卖点",
    "互动文案",
    "上架预热",
    "直播话术",
    "脚本",
)
ANALYST_KEYWORDS = (
    "复盘",
    "报告",
    "总结",
    "统计",
    "分析",
    "高频问题",
    "表现",
    "转化分析",
)
LIVE_CONTEXT_KEYWORDS = (
    "今天这场直播",
    "主推",
    "现在卖",
    "当前商品",
    "当前讲解",
    "直播阶段",
    "今天播什么",
    "今天卖什么",
    "这场直播",
)
DETAIL_KEYWORDS = (
    "价格",
    "多少钱",
    "规格",
    "参数",
    "功率",
    "容量",
    "尺寸",
    "材质",
    "成分",
    "型号",
    "技术",
    "性能",
    "适合",
    "区别",
    "对比",
    "卖点",
    "细节",
    "配置",
    "功能",
    "特点",
)
FAQ_KEYWORDS = (
    "运费",
    "发货",
    "物流",
    "售后",
    "保修",
    "退货",
    "退款",
    "换货",
    "赠品",
    "下单",
    "支付",
    "发票",
    "包邮",
    "多久",
    "质保",
    "注意事项",
    "怎么清洗",
    "怎么安装",
    "使用说明",
    "客服",
    "规则",
)
SMALL_TALK_KEYWORDS = (
    "你好",
    "在吗",
    "哈哈",
    "hi",
    "hello",
    "random",
)
VAGUE_DIRECT_PATTERNS = (
    "说点什么",
    "随便说点",
    "来一句",
    "来点内容",
    "说两句",
)
TOOL_INTENT_NONE = "none"
TOOL_INTENT_DATETIME = "datetime"
TOOL_INTENT_MEMORY_RECALL = "memory_recall"
TOOL_INTENT_WEB_SEARCH = "web_search"
VALID_TOOL_INTENTS = (
    TOOL_INTENT_NONE,
    TOOL_INTENT_DATETIME,
    TOOL_INTENT_MEMORY_RECALL,
    TOOL_INTENT_WEB_SEARCH,
)
PLANNER_MODE_FUNCTION_CALLING = "function_calling"
PLANNER_MODE_HEURISTIC = "heuristic"
PLANNER_ACTION_CALL_DATETIME = "call_datetime"
PLANNER_ACTION_CALL_WEB_SEARCH = "call_web_search"
PLANNER_ACTION_RECALL_MEMORY = "recall_memory"
PLANNER_ACTION_RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
PLANNER_ACTION_HANDOFF_AGENT = "handoff_agent"
PLANNER_TOOL_ACTIONS = {
    PLANNER_ACTION_CALL_DATETIME,
    PLANNER_ACTION_CALL_WEB_SEARCH,
    PLANNER_ACTION_RECALL_MEMORY,
    PLANNER_ACTION_RETRIEVE_KNOWLEDGE,
}
TOOL_INTENT_FALLBACK_DATETIME_KEYWORDS = (
    "今天周几",
    "今天是周几",
    "今天星期几",
    "今天是星期几",
    "礼拜几",
    "周几",
    "星期几",
    "现在几点",
    "几点了",
    "几号",
    "几月几号",
    "当前日期",
    "当前时间",
    "日期",
    "时间",
)
TOOL_INTENT_FALLBACK_MEMORY_HINT_KEYWORDS = (
    "刚刚",
    "刚才",
    "上一轮",
    "上一个",
    "前面",
    "之前",
    "记得",
    "回顾",
    "回忆",
)
TOOL_INTENT_FALLBACK_MEMORY_TARGET_KEYWORDS = (
    "我问",
    "问你的",
    "问题",
    "提问",
    "你说",
    "你回答",
    "回答了",
    "回复",
    "答复",
    "聊了什么",
    "聊到什么",
    "对话",
    "内容",
)
TOOL_INTENT_FALLBACK_WEB_SEARCH_KEYWORDS = (
    "最新",
    "实时",
    "新闻",
    "官网",
    "搜索",
    "搜一下",
    "查一下",
    "帮我查",
    "联网查",
    "上网查",
    "天气",
    "汇率",
    "股价",
    "金价",
    "油价",
    "票房",
    "行情",
)


class PlannerDecision(BaseModel):
    intent: IntentType
    confidence: float
    reason: str
    route_target: str = "qa"
    requires_retrieval: bool = True
    knowledge_scope: str = "mixed"
    tool_intent: str = TOOL_INTENT_NONE
    planner_action: str = PLANNER_ACTION_HANDOFF_AGENT
    planner_action_args: dict[str, Any] = {}
    planner_mode: str = PLANNER_MODE_FUNCTION_CALLING
    fallback_reason: str | None = None
    low_confidence: bool = False


class RouterAgent(BaseAgent):
    name = "router"

    def __init__(self, llm_gateway: LLMGateway):
        self.llm_gateway = llm_gateway

    def _build_prompts(self, state: LiveAgentState) -> tuple[str, str]:
        system_prompt = (
            "你是直播电商系统的 Planner Router，不直接回答用户，只负责决定下一步系统动作。\n"
            "你必须始终调用且只调用一个函数，绝不要直接输出自然语言答案。\n"
            "你的目标是用最短、最稳的路径完成任务。\n"
            "规则：\n"
            "1. 日期、时间、今天周几、今天星期几、礼拜几、现在几点，优先调用 call_datetime。\n"
            "2. 回忆刚刚问了什么、上一轮你怎么回答的、之前聊了什么，调用 recall_memory。\n"
            "3. 需要最新、实时、外部世界信息，例如新闻、天气、汇率、股价、金价、官网，调用 call_web_search。\n"
            "4. 商品参数、适用场景、对比、物流、售后、FAQ、规则类问题，先调用 retrieve_knowledge；"
            "拿到 observation 后，通常再调用 handoff_agent 把结果交给 qa。\n"
            "5. 需要生成话术、口播、促单文案时，调用 handoff_agent，agent=script。\n"
            "6. 需要复盘、统计、分析、报告时，调用 handoff_agent，agent=analyst。\n"
            "7. 打招呼、噪声、极简闲聊、直播上下文确认、简单直答，调用 handoff_agent，agent=direct。\n"
            "8. 如果已经有 observation，不要重复调用同一个工具；应基于 observation 继续规划，通常是 handoff_agent。\n"
            "9. 如果 retrieved_docs 已经存在，优先 handoff_agent 给 qa，不要再次 retrieve。\n"
            "10. handoff_agent 时，intent 只能是 qa|script|analyst|unknown。\n"
            "11. knowledge_scope 只能是 product_detail|faq|mixed。"
        )
        user_prompt = json.dumps(
            {
                "user_input": state["user_input"],
                "live_stage": state.get("live_stage"),
                "current_product_id": state.get("current_product_id"),
                "short_term_memory": self._recent_memory(state, limit=4),
                "planner_step_count": int(state.get("planner_step_count", 0) or 0),
                "planner_trace": self._recent_planner_trace(state, limit=4),
                "executor_observations": self._recent_observations(state, limit=4),
                "retrieved_docs": self._compact_docs(state.get("retrieved_docs", [])),
                "tool_intent": self._normalize_tool_intent(state.get("tool_intent")),
                "few_shots": [
                    {
                        "input": "今天是周几？",
                        "next_action": {"name": "call_datetime", "arguments": {"reason": "用户在问当前星期信息"}},
                    },
                    {
                        "input": "刚刚我问你的是什么问题？",
                        "next_action": {"name": "recall_memory", "arguments": {"reason": "用户在回溯上一轮对话"}},
                    },
                    {
                        "input": "今日黄金金价是多少？",
                        "next_action": {"name": "call_web_search", "arguments": {"query": "今日黄金金价是多少", "reason": "需要实时外部信息"}},
                    },
                    {
                        "input": "这款拖洗一体机适合什么家庭用？",
                        "next_action": {
                            "name": "retrieve_knowledge",
                            "arguments": {
                                "query": "这款拖洗一体机适合什么家庭用？",
                                "knowledge_scope": "product_detail",
                                "reason": "需要先从知识库拿证据",
                            },
                        },
                    },
                    {
                        "input": "帮我写一段促单话术，强调库存快没了。",
                        "next_action": {
                            "name": "handoff_agent",
                            "arguments": {
                                "agent": "script",
                                "intent": "script",
                                "knowledge_scope": "mixed",
                                "reason": "这是话术生成请求，应交给 script agent",
                            },
                        },
                    },
                ],
            },
            ensure_ascii=False,
        )
        return system_prompt, user_prompt

    def _planner_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": PLANNER_ACTION_CALL_DATETIME,
                    "description": "当用户需要当前日期、时间、星期、周几、礼拜几时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": PLANNER_ACTION_RECALL_MEMORY,
                    "description": "当用户在回溯刚刚的问题、上一轮回答或最近对话内容时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": PLANNER_ACTION_CALL_WEB_SEARCH,
                    "description": "当用户需要最新、实时、外部世界信息时调用，例如新闻、天气、汇率、股价、金价、官网。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": PLANNER_ACTION_RETRIEVE_KNOWLEDGE,
                    "description": "当用户问题需要内部知识库证据时调用，用于商品详情、FAQ、规则、参数、适用场景等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "knowledge_scope": {
                                "type": "string",
                                "enum": ["product_detail", "faq", "mixed"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["query", "knowledge_scope"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": PLANNER_ACTION_HANDOFF_AGENT,
                    "description": "当已经拿到足够信息，或者问题本就该交给某个业务 agent 时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent": {
                                "type": "string",
                                "enum": ["qa", "direct", "script", "analyst"],
                            },
                            "intent": {
                                "type": "string",
                                "enum": ["qa", "script", "analyst", "unknown"],
                            },
                            "knowledge_scope": {
                                "type": "string",
                                "enum": ["product_detail", "faq", "mixed"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["agent", "intent", "knowledge_scope"],
                    },
                },
            },
        ]

    def _normalize_query(self, query: str) -> str:
        return re.sub(r"\s+", " ", str(query or "")).strip()

    def _normalize_tool_intent(self, tool_intent: Any) -> str:
        normalized = str(tool_intent or TOOL_INTENT_NONE).strip().lower()
        if normalized in VALID_TOOL_INTENTS:
            return normalized
        return TOOL_INTENT_NONE

    def _contains_any(self, query: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in query for keyword in keywords)

    def _is_noise_input(self, query: str) -> bool:
        compact = query.strip()
        if not compact:
            return True
        if len(compact) <= 2 and not re.search(r"[\u4e00-\u9fffA-Za-z]", compact):
            return True
        if NOISE_PATTERN.fullmatch(compact):
            return True
        if REPEATED_CHAR_PATTERN.fullmatch(compact):
            return True
        return False

    def _is_live_context_question(self, query: str) -> bool:
        return self._contains_any(query, LIVE_CONTEXT_KEYWORDS)

    def _is_vague_direct_query(self, query: str) -> bool:
        normalized = self._normalize_query(query)
        return self._contains_any(normalized, VAGUE_DIRECT_PATTERNS)

    def _infer_knowledge_scope(self, query: str) -> str:
        detail_hits = sum(keyword in query for keyword in DETAIL_KEYWORDS)
        faq_hits = sum(keyword in query for keyword in FAQ_KEYWORDS)
        if detail_hits and faq_hits:
            return "mixed"
        if detail_hits:
            return "product_detail"
        if faq_hits:
            return "faq"
        return "mixed"

    # 主路径依赖函数调用；这里只在模型失效或漏判时兜底。
    def _infer_tool_intent_fallback(self, query: str) -> str:
        normalized = self._normalize_query(query).lower()
        if self._contains_any(normalized, TOOL_INTENT_FALLBACK_DATETIME_KEYWORDS):
            return TOOL_INTENT_DATETIME
        if self._contains_any(normalized, TOOL_INTENT_FALLBACK_MEMORY_HINT_KEYWORDS) and self._contains_any(
            normalized, TOOL_INTENT_FALLBACK_MEMORY_TARGET_KEYWORDS
        ):
            return TOOL_INTENT_MEMORY_RECALL
        if self._contains_any(normalized, TOOL_INTENT_FALLBACK_WEB_SEARCH_KEYWORDS):
            return TOOL_INTENT_WEB_SEARCH
        return TOOL_INTENT_NONE

    def _recent_memory(self, state: LiveAgentState, limit: int) -> list[dict[str, str]]:
        history = list(state.get("short_term_memory", []))
        if not history:
            return []
        return history[-limit:]

    def _compact_docs(self, docs: Any, *, limit: int = 3) -> list[dict[str, Any]]:
        if not isinstance(docs, list):
            return []
        compact: list[dict[str, Any]] = []
        for item in docs[:limit]:
            compact.append(
                {
                    "doc_id": str(item.get("doc_id", "")).strip(),
                    "score": item.get("score"),
                    "source_type": str(item.get("source_type", "")).strip(),
                    "content_preview": str(item.get("content", "")).strip()[:160],
                }
            )
        return compact

    def _recent_planner_trace(self, state: LiveAgentState, limit: int) -> list[dict[str, Any]]:
        trace = list(state.get("planner_trace", []))
        if not trace:
            return []
        return trace[-limit:]

    def _recent_observations(self, state: LiveAgentState, limit: int) -> list[dict[str, Any]]:
        observations = list(state.get("executor_observations", []))
        if not observations:
            return []
        return observations[-limit:]

    def _append_trace(self, state: LiveAgentState, decision: PlannerDecision) -> list[dict[str, Any]]:
        trace = list(state.get("planner_trace", []))
        trace.append(
            {
                "step": int(state.get("planner_step_count", 0) or 0) + 1,
                "planner_action": decision.planner_action,
                "planner_action_args": decision.planner_action_args,
                "route_target": decision.route_target,
                "intent": decision.intent.value,
                "tool_intent": decision.tool_intent,
                "reason": decision.reason,
                "planner_mode": decision.planner_mode,
            }
        )
        return trace

    def _decision_from_tool_call(
        self,
        *,
        state: LiveAgentState,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        planner_mode: str,
        confidence: float,
        fallback_reason: str | None = None,
        low_confidence: bool = False,
    ) -> PlannerDecision:
        args = dict(arguments or {})
        reason = str(args.get("reason", "") or "").strip()
        normalized_query = self._normalize_query(str(state.get("user_input", "")))
        default_scope = self._infer_knowledge_scope(normalized_query)

        if tool_name == PLANNER_ACTION_CALL_DATETIME:
            return PlannerDecision(
                intent=IntentType.qa,
                confidence=confidence,
                reason=reason or "planner selected datetime tool",
                route_target="qa",
                requires_retrieval=False,
                knowledge_scope="mixed",
                tool_intent=TOOL_INTENT_DATETIME,
                planner_action=tool_name,
                planner_action_args=args,
                planner_mode=planner_mode,
                fallback_reason=fallback_reason,
                low_confidence=low_confidence,
            )

        if tool_name == PLANNER_ACTION_CALL_WEB_SEARCH:
            args["query"] = self._normalize_query(str(args.get("query") or normalized_query))
            return PlannerDecision(
                intent=IntentType.qa,
                confidence=confidence,
                reason=reason or "planner selected web search tool",
                route_target="qa",
                requires_retrieval=False,
                knowledge_scope="mixed",
                tool_intent=TOOL_INTENT_WEB_SEARCH,
                planner_action=tool_name,
                planner_action_args=args,
                planner_mode=planner_mode,
                fallback_reason=fallback_reason,
                low_confidence=low_confidence,
            )

        if tool_name == PLANNER_ACTION_RECALL_MEMORY:
            return PlannerDecision(
                intent=IntentType.qa,
                confidence=confidence,
                reason=reason or "planner selected memory recall tool",
                route_target="qa",
                requires_retrieval=False,
                knowledge_scope="mixed",
                tool_intent=TOOL_INTENT_MEMORY_RECALL,
                planner_action=tool_name,
                planner_action_args=args,
                planner_mode=planner_mode,
                fallback_reason=fallback_reason,
                low_confidence=low_confidence,
            )

        if tool_name == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
            args["query"] = self._normalize_query(str(args.get("query") or normalized_query))
            args["knowledge_scope"] = str(args.get("knowledge_scope") or default_scope)
            return PlannerDecision(
                intent=IntentType.qa,
                confidence=confidence,
                reason=reason or "planner selected internal retrieval",
                route_target="qa",
                requires_retrieval=True,
                knowledge_scope=args["knowledge_scope"],
                tool_intent=TOOL_INTENT_NONE,
                planner_action=tool_name,
                planner_action_args=args,
                planner_mode=planner_mode,
                fallback_reason=fallback_reason,
                low_confidence=low_confidence,
            )

        if tool_name == PLANNER_ACTION_HANDOFF_AGENT:
            agent = str(args.get("agent") or "qa").strip().lower()
            if agent not in {"qa", "direct", "script", "analyst"}:
                agent = "qa"
            intent_text = str(args.get("intent") or ("unknown" if agent == "direct" else agent)).strip().lower()
            if intent_text not in {"qa", "script", "analyst", "unknown"}:
                intent_text = "qa"
            knowledge_scope = str(args.get("knowledge_scope") or default_scope).strip().lower()
            if knowledge_scope not in {"product_detail", "faq", "mixed"}:
                knowledge_scope = default_scope
            requires_retrieval = agent in {"qa", "script"}
            if agent == "qa" and (state.get("retrieved_docs") or self._normalize_tool_intent(state.get("tool_intent")) != TOOL_INTENT_NONE):
                requires_retrieval = False
            if agent in {"direct", "analyst"}:
                requires_retrieval = False
            return PlannerDecision(
                intent=IntentType(intent_text),
                confidence=confidence,
                reason=reason or f"planner handed off to {agent}",
                route_target=agent,
                requires_retrieval=requires_retrieval,
                knowledge_scope=knowledge_scope,
                tool_intent=self._normalize_tool_intent(state.get("tool_intent")),
                planner_action=tool_name,
                planner_action_args={
                    "agent": agent,
                    "intent": intent_text,
                    "knowledge_scope": knowledge_scope,
                    "reason": reason,
                },
                planner_mode=planner_mode,
                fallback_reason=fallback_reason,
                low_confidence=low_confidence,
            )

        return PlannerDecision(
            intent=IntentType.qa,
            confidence=confidence,
            reason=reason or "planner fallback to qa handoff",
            route_target="qa",
            requires_retrieval=not bool(state.get("retrieved_docs")),
            knowledge_scope=default_scope,
            tool_intent=self._normalize_tool_intent(state.get("tool_intent")),
            planner_action=PLANNER_ACTION_HANDOFF_AGENT,
            planner_action_args={
                "agent": "qa",
                "intent": "qa",
                "knowledge_scope": default_scope,
                "reason": reason or "fallback handoff to qa",
            },
            planner_mode=planner_mode,
            fallback_reason=fallback_reason,
            low_confidence=low_confidence,
        )

    def _heuristic_follow_up(self, state: LiveAgentState) -> PlannerDecision | None:
        if state.get("retrieved_docs"):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": state.get("knowledge_scope") or "mixed",
                    "reason": "已拿到知识库 observation，交给 qa 生成最终回答",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.74,
            )

        observations = list(state.get("executor_observations", []))
        if observations and str(observations[-1].get("kind", "")).strip() == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": state.get("knowledge_scope") or "mixed",
                    "reason": "知识检索已执行过，避免重复检索，交给 qa 兜底",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.7,
            )

        tool_intent = self._normalize_tool_intent(state.get("tool_intent"))
        if tool_intent in {TOOL_INTENT_DATETIME, TOOL_INTENT_MEMORY_RECALL, TOOL_INTENT_WEB_SEARCH}:
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": "mixed",
                    "reason": "工具 observation 已就绪，交给 qa 生成最终回答",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.74,
            )
        return None

    def _heuristic_plan(self, state: LiveAgentState, *, fallback_reason: str | None = None) -> PlannerDecision:
        follow_up = self._heuristic_follow_up(state)
        if follow_up is not None:
            follow_up.fallback_reason = fallback_reason or follow_up.fallback_reason
            if fallback_reason:
                follow_up.low_confidence = True
            return follow_up

        query = self._normalize_query(str(state.get("user_input", "")))
        lowered = query.lower()
        knowledge_scope = self._infer_knowledge_scope(query)
        tool_intent = self._infer_tool_intent_fallback(query)

        if self._is_noise_input(query):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "direct",
                    "intent": "unknown",
                    "knowledge_scope": "mixed",
                    "reason": "噪声输入走 direct",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.66,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if self._contains_any(lowered, SMALL_TALK_KEYWORDS) or self._is_vague_direct_query(query):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "direct",
                    "intent": "unknown",
                    "knowledge_scope": "mixed",
                    "reason": "闲聊或模糊指令走 direct",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.7,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if self._contains_any(query, SCRIPT_KEYWORDS):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "script",
                    "intent": "script",
                    "knowledge_scope": knowledge_scope,
                    "reason": "命中话术类请求",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.76,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if self._contains_any(query, ANALYST_KEYWORDS):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "analyst",
                    "intent": "analyst",
                    "knowledge_scope": "mixed",
                    "reason": "命中复盘分析类请求",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.76,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if self._is_live_context_question(query):
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "direct",
                    "intent": "qa",
                    "knowledge_scope": "mixed",
                    "reason": "直播上下文确认问题走 direct",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.74,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if tool_intent == TOOL_INTENT_DATETIME:
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_CALL_DATETIME,
                arguments={"reason": "日期时间类问题"},
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.78,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if tool_intent == TOOL_INTENT_MEMORY_RECALL:
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_RECALL_MEMORY,
                arguments={"reason": "对话回溯类问题"},
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.78,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        if tool_intent == TOOL_INTENT_WEB_SEARCH:
            return self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_CALL_WEB_SEARCH,
                arguments={"query": query, "reason": "外部实时信息问题"},
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.78,
                fallback_reason=fallback_reason,
                low_confidence=bool(fallback_reason),
            )

        return self._decision_from_tool_call(
            state=state,
            tool_name=PLANNER_ACTION_RETRIEVE_KNOWLEDGE,
            arguments={
                "query": query,
                "knowledge_scope": knowledge_scope,
                "reason": "默认进入知识检索后再决定最终回答",
            },
            planner_mode=PLANNER_MODE_HEURISTIC,
            confidence=0.72,
            fallback_reason=fallback_reason,
            low_confidence=bool(fallback_reason),
        )

    def _step_limit_fallback(self, state: LiveAgentState) -> PlannerDecision:
        follow_up = self._heuristic_follow_up(state)
        if follow_up is not None:
            follow_up.fallback_reason = "max_steps"
            follow_up.low_confidence = True
            return follow_up
        return self._heuristic_plan(state, fallback_reason="max_steps")

    async def run(self, state: LiveAgentState) -> StatePatch:
        start = time.perf_counter()
        step_count = int(state.get("planner_step_count", 0) or 0)
        tool_intent = self._normalize_tool_intent(state.get("tool_intent"))
        has_tool_observation = bool(state.get("tool_outputs")) and not bool(state.get("agent_output"))

        if step_count >= settings.PLANNER_MAX_STEPS:
            decision = self._step_limit_fallback(state)
        elif tool_intent == TOOL_INTENT_WEB_SEARCH and has_tool_observation:
            # web_search 已经执行过时，planner 直接进入 handoff，确保走 observation -> qa 的统一闭环。
            decision = self._decision_from_tool_call(
                state=state,
                tool_name=PLANNER_ACTION_HANDOFF_AGENT,
                arguments={
                    "agent": "qa",
                    "intent": "qa",
                    "knowledge_scope": "mixed",
                    "reason": "web_search observation 已就绪，交给 qa 生成最终回答",
                },
                planner_mode=PLANNER_MODE_HEURISTIC,
                confidence=0.88,
            )
        else:
            system_prompt, user_prompt = self._build_prompts(state)
            try:
                payload = await self.llm_gateway.ainvoke_tool_call(
                    system_prompt,
                    user_prompt,
                    self._planner_tools(),
                )
                tool_name = str(payload.get("tool_name", "") or "").strip()
                arguments = payload.get("arguments", {})
                if tool_name not in PLANNER_TOOL_ACTIONS | {PLANNER_ACTION_HANDOFF_AGENT}:
                    decision = self._heuristic_plan(state, fallback_reason="planner_no_tool_call")
                else:
                    decision = self._decision_from_tool_call(
                        state=state,
                        tool_name=tool_name,
                        arguments=arguments,
                        planner_mode=PLANNER_MODE_FUNCTION_CALLING,
                        confidence=0.93,
                    )
            except TimeoutError:
                decision = self._heuristic_plan(state, fallback_reason="planner_timeout")
            except Exception as exc:
                logger.warning("planner_function_call_failed trace_id=%s error=%s", state.get("trace_id"), exc)
                decision = self._heuristic_plan(state, fallback_reason="planner_error")

        planner_trace = self._append_trace(state, decision)
        planner_step_count = step_count + 1
        duration_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "planner_decision trace_id=%s step=%s action=%s route_target=%s intent=%s tool_intent=%s mode=%s duration_ms=%s fallback_reason=%s",
            state.get("trace_id"),
            planner_step_count,
            decision.planner_action,
            decision.route_target,
            decision.intent.value,
            decision.tool_intent,
            decision.planner_mode,
            duration_ms,
            decision.fallback_reason,
        )

        return {
            "intent": decision.intent.value,
            "intent_confidence": decision.confidence,
            "route_reason": decision.reason,
            "route_target": decision.route_target,
            "requires_retrieval": decision.requires_retrieval,
            "knowledge_scope": decision.knowledge_scope,
            "tool_intent": decision.tool_intent,
            "planner_mode": decision.planner_mode,
            "planner_action": decision.planner_action,
            "planner_action_args": decision.planner_action_args,
            "planner_step_count": planner_step_count,
            "planner_trace": planner_trace,
            "planning_completed": False,
            "route_fallback_reason": decision.fallback_reason,
            "route_low_confidence": decision.low_confidence,
            "agent_name": self.name,
        }
