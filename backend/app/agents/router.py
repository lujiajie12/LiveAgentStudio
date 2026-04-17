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
            "\n"
            "【必须路由到 qa 的情况】\n"
            "- 商品参数、价格、规格、型号、材质\n"
            "- 适合人群、适用场景、售后政策\n"
            "- 物流、发货、退换货\n"
            "- FAQ 类问题\n"
            "\n"
            "【其他路由】\n"
            "- 日期时间（今天周几/现在几点）：executor + call_datetime\n"
            "- 联网搜索（查一下/搜索）：executor + call_web_search\n"
            "- 记忆回溯（回忆刚才）：executor + recall_memory\n"
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

    async def route(self, state: LiveAgentState) -> StatePatch:
        """轻量路由接口，直接返回 LangGraph 节点名称和工具决策。"""
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
                "agent_name": self.name,
            }

            # 当 route=executor 时，设置 planner_action 和 planner_action_args
            if route == self.ROUTE_TOOLS and tool_action:
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
                    route_target = self.ROUTE_TOOLS
                return {
                    "route_target": route_target,
                    "route_reason": f"heuristic_fallback(json_parse_failed): {heuristic.get('reason', '')}",
                    "intent": intent,
                    "tool_intent": tool_intent,
                    "route_low_confidence": True,
                    "agent_name": self.name,
                }
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": "json_parse_failed",
                "intent": "direct",
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
                    route_target = self.ROUTE_TOOLS
                return {
                    "route_target": route_target,
                    "route_reason": f"heuristic_fallback: {heuristic.get('reason', '')}",
                    "intent": intent,
                    "tool_intent": tool_intent,
                    "route_low_confidence": True,
                    "agent_name": self.name,
                }
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": str(exc),
                "intent": "qa",
                "route_low_confidence": True,
                "agent_name": self.name,
            }
