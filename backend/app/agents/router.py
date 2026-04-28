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

    def _contains_any(self, text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _tool_action_for_input(self, text: str) -> str | None:
        if self._contains_any(text, ("\u8bb0\u4f4f", "\u8bf7\u8bb0\u4f4f")):
            return None

        memory_hints = (
            "\u521a\u521a",
            "\u521a\u624d",
            "\u4e0a\u4e00\u8f6e",
            "\u4e0a\u4e00\u4e2a",
            "\u524d\u9762",
            "\u4e4b\u524d",
            "\u8bb0\u5f97",
            "\u56de\u987e",
            "\u56de\u5fc6",
        )
        memory_targets = (
            "\u6211\u95ee",
            "\u95ee\u9898",
            "\u63d0\u95ee",
            "\u4f60\u8bf4",
            "\u4f60\u56de\u7b54",
            "\u56de\u7b54",
            "\u56de\u590d",
            "\u804a\u4e86",
            "\u804a\u5230",
            "\u5bf9\u8bdd",
            "\u5185\u5bb9",
            "\u504f\u597d",
            "faq",
            "\u53d1\u8d27",
            "\u8fd0\u8d39",
        )
        if self._contains_any(text, memory_hints) and self._contains_any(text, memory_targets):
            return PLANNER_ACTION_RECALL_MEMORY
        if "\u504f\u597d" in text and self._contains_any(
            text,
            ("\u4ec0\u4e48", "\u662f\u4ec0\u4e48", "\u8fd8\u8bb0\u5f97", "\u8bb0\u5f97", "\u6211\u7684", "\u540e\u7eed"),
        ):
            return PLANNER_ACTION_RECALL_MEMORY
        if "faq" in text and self._contains_any(text, ("\u56de\u5fc6", "\u8bb0\u5f97", "\u4e4b\u524d", "\u8bb0\u5f55")):
            return PLANNER_ACTION_RECALL_MEMORY

        datetime_terms = (
            "\u5468\u51e0",
            "\u661f\u671f\u51e0",
            "\u51e0\u70b9",
            "\u51e0\u53f7",
            "\u51e0\u6708\u51e0\u53f7",
            "\u5f53\u524d\u65e5\u671f",
            "\u5f53\u524d\u65f6\u95f4",
            "\u73b0\u5728\u662f\u4e0a\u5348",
            "\u73b0\u5728\u662f\u4e0b\u5348",
        )
        relative_date_terms = (
            "\u660e\u5929",
            "\u540e\u5929",
            "\u4e0b\u5468",
            "\u672c\u5468",
            "\u4e09\u5929\u540e",
            "\u4e0b\u4e2a\u6708",
            "\u6708\u5e95",
        )
        if self._contains_any(text, datetime_terms) or (
            self._contains_any(text, relative_date_terms)
            and self._contains_any(text, ("\u662f", "\u8ddd\u79bb", "\u8fd8\u6709"))
        ):
            return PLANNER_ACTION_CALL_DATETIME

        web_terms = (
            "\u6700\u65b0",
            "\u5b9e\u65f6",
            "\u65b0\u95fb",
            "\u5b98\u7f51",
            "\u641c\u7d22",
            "\u641c\u4e00\u4e0b",
            "\u67e5\u4e00\u4e0b",
            "\u8054\u7f51\u67e5",
            "\u4e0a\u7f51\u67e5",
            "\u5929\u6c14",
            "\u6c47\u7387",
            "\u80a1\u4ef7",
            "\u91d1\u4ef7",
            "\u6cb9\u4ef7",
        )
        if self._contains_any(text, web_terms):
            return PLANNER_ACTION_CALL_WEB_SEARCH
        return None

    def _looks_direct(self, text: str) -> bool:
        direct_terms = (
            "hi",
            "hello",
            "\u4f60\u597d",
            "\u60a8\u597d",
            "\u5728\u5417",
            "\u4f60\u662f\u8c01",
            "\u4f60\u662f\u4ec0\u4e48",
            "\u4ec0\u4e48agent",
            "\u76f4\u64ad\u4e2d\u53f0\u52a9\u624b",
            "\u4f60\u80fd\u505a\u4ec0\u4e48",
            "\u80fd\u505a\u4ec0\u4e48",
            "\u4ecb\u7ecd\u4e00\u4e0b\u4f60",
            "\u4ecb\u7ecd\u4e00\u4e0b\u4f60\u7684\u80fd\u529b",
            "\u4f60\u7684\u80fd\u529b",
            "\u4f60\u7684\u529f\u80fd",
            "\u6709\u4ec0\u4e48\u529f\u80fd",
            "\u7cfb\u7edf\u80fd\u529b",
            "\u4f60\u7684\u804c\u8d23",
            "\u4e00\u53e5\u8bdd\u8bf4\u660e",
            "\u6d4b\u8bd5\u4e00\u4e0b\u8fde\u63a5",
            "\u6536\u5230",
            "\u51c6\u5907\u5f00\u59cb",
            "\u5148\u4e0d\u8981\u67e5\u5546\u54c1",
            "\u6253\u4e2a\u62db\u547c",
            "\u652f\u6301\u54ea\u4e9b\u667a\u80fd\u4f53",
            "\u667a\u80fd\u4f53\u80fd\u529b",
            "\u8bf4\u70b9\u4ec0\u4e48",
        )
        if self._contains_any(text, direct_terms):
            return True
        return "\u8fd9\u573a\u76f4\u64ad" in text and "\u4e3b\u63a8" in text

    def _looks_analyst(self, text: str) -> bool:
        return self._contains_any(
            text,
            (
                "\u590d\u76d8",
                "\u6570\u636e\u5206\u6790",
                "\u7edf\u8ba1",
                "\u62a5\u544a",
                "\u4f18\u5316\u5efa\u8bae",
                "\u8fd0\u8425\u5efa\u8bae",
                "\u8f6c\u5316\u8868\u73b0",
                "\u9ad8\u9891\u95ee\u9898",
                "\u672a\u89e3\u51b3\u95ee\u9898",
                "\u603b\u7ed3\u672c\u573a",
                "\u672c\u573a\u76f4\u64ad",
            ),
        )

    def _looks_script(self, text: str) -> bool:
        script_nouns = (
            "\u8bdd\u672f",
            "\u53e3\u64ad",
            "\u811a\u672c",
            "\u6587\u6848",
            "\u77ed\u53e5",
            "\u4fc3\u5355",
            "\u5f00\u573a",
            "\u7559\u4eba",
            "\u79cd\u8349",
            "\u903c\u5355",
            "\u8bb2\u89e3",
            "\u4e3b\u64ad\u53e3\u543b",
            "\u798f\u5229\u6b3e",
            "\u5e93\u5b58\u7d27\u5f20",
            "\u627f\u63a5\u8bdd\u672f",
        )
        script_actions = (
            "\u5199",
            "\u751f\u6210",
            "\u6765\u4e00\u6bb5",
            "\u6539\u6210",
            "\u8f93\u51fa",
            "\u6574\u7406\u6210",
            "\u5e2e\u6211",
            "\u7ed9",
            "\u628a",
            "\u7528",
        )
        if "\u4e3b\u64ad\u53e3\u543b" in text:
            return True
        return self._contains_any(text, script_nouns) and self._contains_any(text, script_actions)

    def _looks_memory_write_or_preference(self, text: str) -> bool:
        return self._contains_any(
            text,
            (
                "\u8bb0\u4f4f",
                "\u8bf7\u8bb0\u4f4f",
                "\u8bb0\u5f55",
                "\u4ee5\u540e",
                "\u957f\u671f",
                "\u504f\u597d",
                "\u6211\u559c\u6b22",
                "\u6211\u66f4\u559c\u6b22",
                "\u6211\u7684\u504f\u597d",
                "\u4e60\u60ef",
            ),
        )

    def _rule_based_route(self, state: LiveAgentState) -> StatePatch | None:
        user_input = str(state.get("user_input", "") or "").strip().lower()
        text = re.sub(r"\s+", "", user_input)
        if not text:
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": "rule_boundary:empty_input",
                "intent": "direct",
                "route_low_confidence": False,
                "agent_name": self.name,
            }

        tool_action = self._tool_action_for_input(text)
        if tool_action:
            tool_intent = TOOL_INTENT_NONE
            args: dict[str, str] = {"reason": "rule_boundary:tool_intent"}
            if tool_action == PLANNER_ACTION_CALL_DATETIME:
                tool_intent = TOOL_INTENT_DATETIME
            elif tool_action == PLANNER_ACTION_CALL_WEB_SEARCH:
                tool_intent = TOOL_INTENT_WEB_SEARCH
                args["query"] = str(state.get("user_input", ""))
            elif tool_action == PLANNER_ACTION_RECALL_MEMORY:
                tool_intent = TOOL_INTENT_MEMORY_RECALL
            return {
                "route_target": self.ROUTE_TOOLS,
                "route_reason": f"rule_boundary:{tool_action}",
                "route_low_confidence": False,
                "agent_name": self.name,
                "planner_action": tool_action,
                "planner_action_args": args,
                "tool_intent": tool_intent,
                "intent": "qa",
            }

        if self._looks_memory_write_or_preference(text):
            return {
                "route_target": self.ROUTE_QA,
                "route_reason": "rule_boundary:memory_write",
                "intent": "qa",
                "route_low_confidence": False,
                "agent_name": self.name,
            }

        if self._looks_analyst(text):
            return {
                "route_target": self.ROUTE_ANALYST,
                "route_reason": "rule_boundary:analyst",
                "intent": "analyst",
                "route_low_confidence": False,
                "agent_name": self.name,
            }
        if self._looks_script(text):
            return {
                "route_target": self.ROUTE_SCRIPT,
                "route_reason": "rule_boundary:script",
                "intent": "script",
                "route_low_confidence": False,
                "agent_name": self.name,
            }
        if self._looks_direct(text):
            return {
                "route_target": self.ROUTE_DIRECT,
                "route_reason": "rule_boundary:direct",
                "intent": "direct",
                "route_low_confidence": False,
                "agent_name": self.name,
            }
        return None

    async def route(self, state: LiveAgentState) -> StatePatch:
        """轻量路由接口，直接返回 LangGraph 节点名称和工具决策。"""
        rule_based = self._rule_based_route(state)
        if rule_based is not None:
            logger.info(
                "[ROUTER] trace_id=%s rule_route=%s reason=%s user_input=%s",
                state.get("trace_id"),
                rule_based.get("route_target"),
                rule_based.get("route_reason"),
                str(state.get("user_input", ""))[:50],
            )
            return rule_based

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
