import json
import re

from app.agents.base import BaseAgent
from app.core.logging import get_logger
from app.graph.state import LiveAgentState, StatePatch
from app.services.llm_gateway import LLMGateway

logger = get_logger(__name__)

# 工具意图常量（供 runtime.py 使用）
TOOL_INTENT_NONE = "none"
TOOL_INTENT_DATETIME = "datetime"
TOOL_INTENT_MEMORY_RECALL = "memory_recall"
TOOL_INTENT_WEB_SEARCH = "web_search"

# Planner 动作常量（供 runtime.py 使用）
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


class RouterAgent(BaseAgent):
    name = "router"

    # 路由目标枚举，与 LangGraph 节点名称一一对应
    ROUTE_DIRECT = "direct"
    ROUTE_QA = "qa"
    ROUTE_SCRIPT = "script"
    ROUTE_ANALYST = "analyst"
    ROUTE_TOOLS = "executor"  # 需要调用工具（retrieve/web_search/datetime/memory）
    VALID_ROUTES = {ROUTE_DIRECT, ROUTE_QA, ROUTE_SCRIPT, ROUTE_ANALYST, ROUTE_TOOLS}

    def __init__(self, llm_gateway: LLMGateway):
        self.llm_gateway = llm_gateway

    def _build_routing_prompts(self, state: LiveAgentState) -> tuple[str, str]:
        """构建轻量路由分类 prompt，直接返回 LangGraph 节点名称和工具决策。

        这个方法用于快速路由判断，LLM 直接返回：
        - route: 目标节点名称（direct/qa/script/analyst/executor）
        - tool_action: 当 route=executor 时，指定具体工具
        - reason: 判断理由
        """
        system_prompt = (
            "你是 LiveAgent 直播中台系统的路由分类器。\n"
            "你的任务是将用户输入分类到以下路由之一：\n"
            "- direct: 简单直答、身份介绍、能力说明、问候、闲聊\n"
            "- qa: 商品详情、参数规格、价格、售后、物流、FAQ、规则等知识问答\n"
            "- script: 直播话术、口播文案、促单、互动留人等文案生成需求\n"
            "- analyst: 直播复盘、数据分析、统计报告、表现总结\n"
            "- executor: 需要调用工具（见 tool_action）\n"
            "\n"
            "【tool_action 仅在 route=executor 时使用】\n"
            "- call_datetime: 日期时间查询（今天周几/现在几点/明天日期等）\n"
            "- call_web_search: 联网搜索（最新消息/新闻/官网等）\n"
            "- recall_memory: 记忆回溯（回忆刚才问什么/之前聊了什么）\n"
            "- retrieve_knowledge: 知识库检索（商品详情/FQA/规则等，需先查知识库）\n"
            "\n"
            "【强制规则 - 必须严格遵守】\n"
            "1. 只返回纯 JSON 对象，不要包含任何 markdown 代码块标记（如 ```json）\n"
            "2. 直接输出 JSON，不要有任何前缀或后缀文字\n"
            "3. 格式：{\"route\": \"...\", \"tool_action\": \"...\", \"reason\": \"...\"}\n"
            "4. 当 route 不是 executor 时，tool_action 必须是 null\n"
            "5. 不要输出任何解释、说明或额外文字\n"
            "\n"
            "【必须直接路由到 direct 的情况】\n"
            "- 用户问\"你是谁\"、\"你是什么\"、\"你是一款什么agent\"、\"你是做什么的\"、\"介绍一下你自己\"\n"
            "- 用户说\"你好\"、\"在吗\"、\"hi\"、\"hello\" 等问候\n"
            "- 用户问系统能做什么、有什么功能、能力边界\n"
            "- 用户问后台管理系统、Studio、直播操作台、提词器、Agent Flow 的入口、导航、区别、使用说明\n"
            "- 用户只是问\"你能联网搜索吗\"、\"你会记住刚才的问题吗\"这类能力说明，必须 direct，不要调用工具\n"
            "\n"
            "【必须路由到 qa 的情况】\n"
            "- 商品参数、价格、规格、型号、材质\n"
            "- 适合人群、适用场景、售后政策\n"
            "- 物流、发货、退换货\n"
            "- FAQ 类问题\n"
            "\n"
            "【其他路由】\n"
            "- 日期时间（今天周几/现在几点）：executor + call_datetime\n"
            "- 明确要求查外部实时信息（帮我查一下/搜索一下/最新新闻/官网/天气/汇率/金价）：executor + call_web_search\n"
            "- 明确要求回忆历史内容（刚刚我问了什么/上一轮你怎么回答）：executor + recall_memory\n"
            "- 话术/文案生成：script\n"
            "- 复盘/统计/报告：analyst\n"
            "\n"
            "【重要】如果用户只是问你是谁/什么agent/做什么的，必须路由到 direct，不是 qa！\n"
        )
        user_prompt = json.dumps(
            {
                "user_input": state.get("user_input", ""),
                "live_stage": state.get("live_stage"),
                "current_product_id": state.get("current_product_id"),
            },
            ensure_ascii=False,
        )
        return system_prompt, user_prompt

    async def run(self, state: LiveAgentState) -> StatePatch:
        """兼容 BaseAgent，实际调用 route()"""
        return await self.route(state)

    def _parse_json_response(self, response: str) -> dict | None:
        """健壮的 JSON 解析兜底逻辑。"""
        candidates = []

        # 1. 尝试直接解析
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # 2. 尝试清理 markdown 代码块
        cleaned = response.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 2:
                candidates.append(parts[1].lstrip("json\n").rstrip("```").strip())

        # 3. 尝试提取 { ... } JSON 对象
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, cleaned)
        candidates.extend(matches)

        # 4. 尝试每个候选
        for candidate in candidates:
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue

        return None

    def _normalize_query(self, query: str) -> str:
        return re.sub(r"\s+", "", str(query or "")).strip().lower()

    def _handoff_result(
        self,
        route: str,
        reason: str,
        *,
        intent: str | None = None,
        tool_intent: str = TOOL_INTENT_NONE,
        requires_retrieval: bool = False,
        knowledge_scope: str | None = None,
        low_confidence: bool = False,
    ) -> StatePatch:
        resolved_intent = intent or route
        result: StatePatch = {
            "route_target": route,
            "route_reason": reason,
            "intent": resolved_intent,
            "tool_intent": tool_intent,
            "requires_retrieval": requires_retrieval,
            "route_low_confidence": low_confidence,
            "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
            "planner_action_args": {
                "agent": route,
                "intent": resolved_intent,
                "reason": reason,
            },
            "planning_completed": False,
            "agent_name": self.name,
        }
        if knowledge_scope:
            result["knowledge_scope"] = knowledge_scope
        return result

    def _is_web_search_capability_question(self, query: str) -> bool:
        capability_markers = ("你能", "你会", "你可以", "是否支持", "支持", "能不能", "可不可以", "会不会")
        web_topics = ("联网搜索", "联网搜", "联网查", "上网搜索", "上网查", "访问互联网", "网上搜索")
        action_markers = (
            "帮我搜",
            "帮我查",
            "搜一下",
            "查一下",
            "查下",
            "搜索一下",
            "搜索下",
            "最新",
            "实时",
            "新闻",
            "官网",
            "天气",
            "汇率",
            "股价",
            "金价",
            "油价",
        )
        return (
            any(marker in query for marker in capability_markers)
            and any(topic in query for topic in web_topics)
            and not any(marker in query for marker in action_markers)
        )

    def _is_memory_capability_question(self, query: str) -> bool:
        capability_markers = ("你能", "你会", "你可以", "是否支持", "支持", "能不能", "可不可以", "会不会")
        memory_topics = ("记住", "记忆", "保存对话", "保存问题", "记下来")
        return any(marker in query for marker in capability_markers) and any(topic in query for topic in memory_topics)

    def _is_system_navigation_question(self, query: str) -> bool:
        system_terms = (
            "studio",
            "直播操作台",
            "直播操作中台",
            "后台管理系统",
            "后台系统",
            "提词器",
            "agentflow",
            "agent流程",
            "agent链路",
            "页面",
            "入口",
        )
        navigation_terms = (
            "从哪里进入",
            "在哪里进入",
            "怎么进入",
            "如何进入",
            "怎么打开",
            "如何打开",
            "打开",
            "进入",
            "入口",
            "有什么区别",
            "什么区别",
            "区别",
            "怎么看",
            "怎么查看",
            "在哪看",
            "在哪里看",
            "说明",
        )
        return any(term in query for term in system_terms) and any(term in query for term in navigation_terms)

    def _fast_route(self, state: LiveAgentState) -> StatePatch | None:
        observations = list(state.get("executor_observations") or [])
        if observations:
            last_kind = str(observations[-1].get("kind") or "").strip()
            if last_kind == PLANNER_ACTION_CALL_WEB_SEARCH:
                return self._handoff_result(
                    self.ROUTE_QA,
                    "handoff_after_web_search_observation",
                    intent="qa",
                    tool_intent=TOOL_INTENT_WEB_SEARCH,
                    requires_retrieval=False,
                )
            if last_kind == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
                return self._handoff_result(
                    self.ROUTE_QA,
                    "handoff_after_knowledge_retrieval",
                    intent="qa",
                    tool_intent=TOOL_INTENT_NONE,
                    requires_retrieval=False,
                    knowledge_scope=str(state.get("knowledge_scope") or "mixed"),
                )

        query = self._normalize_query(str(state.get("user_input", "")))
        if not query:
            return self._handoff_result(self.ROUTE_DIRECT, "empty_input_direct", intent="direct")
        if (
            self._is_web_search_capability_question(query)
            or self._is_memory_capability_question(query)
            or self._is_system_navigation_question(query)
        ):
            return self._handoff_result(self.ROUTE_DIRECT, "system_or_capability_question_direct", intent="direct")
        return None

    async def route(self, state: LiveAgentState) -> StatePatch:
        """轻量路由接口，直接返回 LangGraph 节点名称和工具决策。"""
        fast_route = self._fast_route(state)
        if fast_route is not None:
            logger.info(
                "[ROUTER] trace_id=%s fast_route=%s reason=%s user_input=%s",
                state.get("trace_id"),
                fast_route.get("route_target"),
                fast_route.get("route_reason"),
                str(state.get("user_input", ""))[:50],
            )
            return fast_route

        system_prompt, user_prompt = self._build_routing_prompts(state)
        try:
            response = await self.llm_gateway.ainvoke_text(system_prompt, user_prompt)
            payload = self._parse_json_response(response)
            if payload is None:
                logger.warning("[ROUTER] all JSON parsing attempts failed, raw response: %s", response[:200])
                return {
                    "route_target": self.ROUTE_DIRECT,
                    "route_reason": "all_json_parse_failed",
                    "intent": "direct",
                    "tool_intent": TOOL_INTENT_NONE,
                    "requires_retrieval": False,
                    "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                    "planner_action_args": {
                        "agent": self.ROUTE_DIRECT,
                        "intent": "direct",
                        "reason": "all_json_parse_failed",
                    },
                    "planning_completed": False,
                    "route_low_confidence": True,
                    "agent_name": self.name,
                }
            route = str(payload.get("route", "")).strip().lower()
            tool_action = str(payload.get("tool_action", "") or "").strip()
            reason = str(payload.get("reason", "")).strip()

            if route not in self.VALID_ROUTES:
                route = self.ROUTE_DIRECT  # 无效 route 默认直答，避免走 RAG

            logger.info(
                "[ROUTER] trace_id=%s route=%s tool_action=%s reason=%s user_input=%s",
                state.get("trace_id"),
                route,
                tool_action,
                reason,
                str(state.get("user_input", ""))[:50],
            )

            result: StatePatch = {
                "route_target": route,
                "route_reason": reason,
                "route_low_confidence": False,
                "tool_intent": TOOL_INTENT_NONE,
                "requires_retrieval": route == self.ROUTE_QA,
                "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                "planner_action_args": {
                    "agent": route,
                    "intent": route if route != self.ROUTE_TOOLS else "qa",
                    "reason": reason,
                },
                "planning_completed": False,
                "agent_name": self.name,
            }

            # 当 route=executor 时，设置 planner_action 和 planner_action_args
            if route == self.ROUTE_TOOLS and tool_action in PLANNER_TOOL_ACTIONS:
                result["planner_action"] = tool_action
                result["intent"] = "qa"
                if tool_action == PLANNER_ACTION_CALL_DATETIME:
                    result["tool_intent"] = TOOL_INTENT_DATETIME
                    result["planner_action_args"] = {"reason": reason}
                elif tool_action == PLANNER_ACTION_CALL_WEB_SEARCH:
                    result["tool_intent"] = TOOL_INTENT_WEB_SEARCH
                    result["planner_action_args"] = {
                        "query": str(state.get("user_input", "")),
                        "reason": reason,
                    }
                elif tool_action == PLANNER_ACTION_RECALL_MEMORY:
                    result["tool_intent"] = TOOL_INTENT_MEMORY_RECALL
                    result["planner_action_args"] = {"reason": reason}
                elif tool_action == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
                    result["tool_intent"] = TOOL_INTENT_NONE
                    result["planner_action_args"] = {
                        "query": str(state.get("user_input", "")),
                        "knowledge_scope": "mixed",
                        "reason": reason,
                    }
            else:
                if route == self.ROUTE_TOOLS:
                    result["route_target"] = self.ROUTE_QA
                    result["route_reason"] = f"{reason}; invalid_or_missing_tool_action_fallback_to_qa"
                    result["planner_action_args"] = {
                        "agent": self.ROUTE_QA,
                        "intent": "qa",
                        "reason": result["route_reason"],
                    }
                result["intent"] = route if route != self.ROUTE_TOOLS else "qa"

            return result
        except json.JSONDecodeError:
            # JSON 解析失败，用启发式规则兜底而非一律走 direct
            logger.warning("[ROUTER] invalid JSON response, falling back to heuristic: %s", response[:200] if response else "empty")
            heuristic_fn = getattr(self.llm_gateway, "_heuristic_response", None)
            if heuristic_fn:
                heuristic = heuristic_fn(user_prompt)
                intent = heuristic.get("intent", "unknown")
                tool_intent = heuristic.get("tool_intent", TOOL_INTENT_NONE)
                intent_to_route = {
                    "qa": self.ROUTE_QA,
                    "script": self.ROUTE_SCRIPT,
                    "analyst": self.ROUTE_ANALYST,
                    "direct": self.ROUTE_DIRECT,
                    "greeting": self.ROUTE_DIRECT,
                }
                route_target = intent_to_route.get(intent, self.ROUTE_QA)
                if tool_intent != TOOL_INTENT_NONE:
                    route_target = self.ROUTE_QA
                return {
                    "route_target": route_target,
                    "route_reason": f"heuristic_fallback(json_parse_failed): {heuristic.get('reason', '')}",
                    "intent": intent,
                    "tool_intent": tool_intent,
                    "requires_retrieval": route_target == self.ROUTE_QA and tool_intent == TOOL_INTENT_NONE,
                    "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                    "planner_action_args": {
                        "agent": route_target,
                        "intent": intent,
                        "reason": f"heuristic_fallback(json_parse_failed): {heuristic.get('reason', '')}",
                    },
                    "planning_completed": False,
                    "route_low_confidence": True,
                    "agent_name": self.name,
                }
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": "json_parse_failed",
                "intent": "direct",
                "tool_intent": TOOL_INTENT_NONE,
                "requires_retrieval": False,
                "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                "planner_action_args": {
                    "agent": self.ROUTE_DIRECT,
                    "intent": "direct",
                    "reason": "json_parse_failed",
                },
                "planning_completed": False,
                "route_low_confidence": True,
                "agent_name": self.name,
            }
        except Exception as exc:
            logger.warning("[ROUTER] route failed: %s, falling back to heuristic", exc)
            # LLM 不可用时，使用启发式规则进行路由分类，而非一律走 direct
            heuristic_fn = getattr(self.llm_gateway, "_heuristic_response", None)
            if heuristic_fn:
                heuristic = heuristic_fn(user_prompt)
                intent = heuristic.get("intent", "unknown")
                tool_intent = heuristic.get("tool_intent", TOOL_INTENT_NONE)
                intent_to_route = {
                    "qa": self.ROUTE_QA,
                    "script": self.ROUTE_SCRIPT,
                    "analyst": self.ROUTE_ANALYST,
                    "direct": self.ROUTE_DIRECT,
                    "greeting": self.ROUTE_DIRECT,
                }
                route_target = intent_to_route.get(intent, self.ROUTE_QA)
                if tool_intent != TOOL_INTENT_NONE:
                    route_target = self.ROUTE_QA
                return {
                    "route_target": route_target,
                    "route_reason": f"heuristic_fallback: {heuristic.get('reason', '')}",
                    "intent": intent,
                    "tool_intent": tool_intent,
                    "requires_retrieval": route_target == self.ROUTE_QA and tool_intent == TOOL_INTENT_NONE,
                    "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                    "planner_action_args": {
                        "agent": route_target,
                        "intent": intent,
                        "reason": f"heuristic_fallback: {heuristic.get('reason', '')}",
                    },
                    "planning_completed": False,
                    "route_low_confidence": True,
                    "agent_name": self.name,
                }
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": str(exc),
                "intent": "qa",
                "tool_intent": TOOL_INTENT_NONE,
                "requires_retrieval": False,
                "planner_action": PLANNER_ACTION_HANDOFF_AGENT,
                "planner_action_args": {
                    "agent": self.ROUTE_DIRECT,
                    "intent": "qa",
                    "reason": str(exc),
                },
                "planning_completed": False,
                "route_low_confidence": True,
                "agent_name": self.name,
            }
