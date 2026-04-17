from time import perf_counter
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.agents.direct_reply_agent import DirectReplyAgent
from app.agents.placeholders import AnalystPlaceholderAgent, ScriptPlaceholderAgent
from app.agents.qa_agent import QAAgent
from app.agents.router import (
    PLANNER_ACTION_CALL_DATETIME,
    PLANNER_ACTION_CALL_WEB_SEARCH,
    PLANNER_ACTION_RECALL_MEMORY,
    PLANNER_ACTION_RETRIEVE_KNOWLEDGE,
    PLANNER_TOOL_ACTIONS,
    TOOL_INTENT_DATETIME,
    TOOL_INTENT_MEMORY_RECALL,
    TOOL_INTENT_NONE,
    TOOL_INTENT_WEB_SEARCH,
    RouterAgent,
)
from app.core.logging import get_logger
from app.core.observability import record_tool_call, record_timed_tool_call
from app.graph.state import LiveAgentState
from app.services.guardrail_service import GuardrailService

logger = get_logger(__name__)


class GraphRuntime:
    def __init__(
        self,
        router_agent: RouterAgent,
        guardrail_service: GuardrailService,
        retrieval_pipeline=None,
        qa_agent: BaseAgent | None = None,
        direct_agent: BaseAgent | None = None,
        script_agent: BaseAgent | None = None,
        analyst_agent: BaseAgent | None = None,
        skill_registry=None,
    ):
        self.router_agent = router_agent
        self.guardrail_service = guardrail_service
        self.skill_registry = skill_registry
        self.qa_agent: BaseAgent = qa_agent or QAAgent(retrieval_pipeline=retrieval_pipeline)
        self.direct_agent: BaseAgent = direct_agent or DirectReplyAgent()
        self.script_agent: BaseAgent = script_agent or ScriptPlaceholderAgent(retrieval_pipeline=retrieval_pipeline)
        self.analyst_agent: BaseAgent = analyst_agent or AnalystPlaceholderAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        # 主图只保留一条统一闭环：
        # planner 负责决策，executor 负责执行工具动作，真正产出回复的 agent 再统一走 guardrail。
        workflow = StateGraph(LiveAgentState)
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("executor", self.executor_node)
        workflow.add_node("qa", self.qa_node)
        workflow.add_node("direct", self.direct_node)
        workflow.add_node("script", self.script_node)
        workflow.add_node("analyst", self.analyst_node)
        workflow.add_node("guardrail", self.guardrail_node)

        workflow.add_edge(START, "planner")
        workflow.add_conditional_edges(
            "planner",
            self.next_after_planner,
            {
                "executor": "executor",
                "qa": "qa",
                "direct": "direct",
                "script": "script",
                "analyst": "analyst",
                "guardrail": "guardrail",
            },
        )
        workflow.add_conditional_edges(
            "executor",
            self.next_after_executor,
            {
                "planner": "planner",
                "guardrail": "guardrail",
            },
        )
        workflow.add_edge("qa", "guardrail")
        workflow.add_edge("direct", "guardrail")
        workflow.add_edge("script", "guardrail")
        workflow.add_edge("analyst", "guardrail")
        workflow.add_edge("guardrail", END)
        return workflow.compile()

    def next_after_planner(self, state: LiveAgentState) -> str:
        # planner 如果返回的是“工具动作”，先进入 executor 执行，再决定是否继续规划。
        planner_action = str(state.get("planner_action") or "").strip()
        if planner_action in PLANNER_TOOL_ACTIONS:
            return "executor"
        # planner 如果直接决定 handoff 到具体 agent，就直接切到对应节点。
        route_target = state.get("route_target")
        if route_target in {"qa", "direct", "script", "analyst"}:
            return route_target
        # 如果规划阶段已经直接产出了可交付结果，或者已经声明规划完成，就直接进入 guardrail。
        if state.get("planning_completed") or state.get("agent_output"):
            return "guardrail"
        # 兜底走 QA，避免图卡死在 planner。
        return "qa"

    def next_after_executor(self, state: LiveAgentState) -> str:
        # executor 执行完工具后有两种情况：
        # 1. 已经拿到了最终回答，直接进 guardrail
        # 2. 只拿到了 observation，回到 planner 再做下一步决策
        if state.get("planning_completed") or state.get("agent_output"):
            return "guardrail"
        return "planner"

    async def _run_node(
        self,
        node_name: str,
        state: LiveAgentState,
        runner: Callable[[LiveAgentState], Awaitable[dict[str, Any]]],
        *,
        category: str,
    ) -> dict[str, Any]:
        # 所有节点统一从这里包一层可观测逻辑，
        # 这样进入、退出、耗时、异常都会自动写入工具日志。
        await record_tool_call(
            f"{node_name}_enter",
            node_name=node_name,
            category=category,
            input_payload={"intent": state.get("intent"), "session_id": state.get("session_id")},
            status="start",
        )
        started = perf_counter()
        try:
            result = await runner(state)
        except Exception as exc:
            await record_timed_tool_call(
                f"{node_name}_exit",
                started_at=started,
                node_name=node_name,
                category=category,
                input_payload={"intent": state.get("intent")},
                output_summary=str(exc),
                status="error",
            )
            raise
        await record_timed_tool_call(
            f"{node_name}_exit",
            started_at=started,
            node_name=node_name,
            category=category,
            input_payload={"intent": state.get("intent")},
            output_summary=self._summarize_result(result),
            status="ok",
        )
        return result

    def _summarize_result(self, result: Any) -> str:
        # 优先摘要真正的回答内容；如果当前节点没有直接回答，则退化成 observation 摘要。
        if isinstance(result, dict):
            summary = str(result.get("agent_output") or result.get("final_output") or "").strip()
            if summary:
                return summary[:200]
            observations = list(result.get("executor_observations", []))
            if observations:
                return str(observations[-1].get("summary", ""))[:200]
        final_output = getattr(result, "final_output", "")
        if final_output:
            return str(final_output)[:200]
        return str(result)[:200]

    def _append_observation(
        self,
        state: LiveAgentState,
        *,
        kind: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        # executor 每执行一步工具，都会在 state 中追加一条 observation。
        # planner 下一轮会读取这里的结果，决定是否继续规划或直接 handoff。
        observations = list(state.get("executor_observations", []))
        observations.append(
            {
                "step": int(state.get("planner_step_count", 0) or 0),
                "kind": kind,
                "summary": summary,
                "payload": payload or {},
            }
        )
        return observations

    async def _execute_planner_action(self, state: LiveAgentState) -> dict[str, Any]:
        # executor 只做一件事：把 planner 选择的动作真正执行掉，
        # 再把结果以 observation 或最终答案的形式回填进 state。
        action = str(state.get("planner_action") or "").strip()
        args = dict(state.get("planner_action_args") or {})

        if action == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
            # retrieve_knowledge 不直接生成答案，只负责把召回结果写回 state，
            # 让 planner 或 qa 在下一步基于这些文档继续决策。
            retrieval_state = dict(state)
            retrieval_state["knowledge_scope"] = str(args.get("knowledge_scope") or state.get("knowledge_scope") or "mixed")
            retrieval_state["rewritten_query"] = str(args.get("query") or state.get("rewritten_query") or state.get("user_input") or "")
            retrieve_only = getattr(self.qa_agent, "retrieve_only", None)
            if retrieve_only is None:
                raise RuntimeError("qa agent does not implement retrieve_only")
            retrieval_result = await retrieve_only(retrieval_state)
            retrieved_docs = list(retrieval_result.get("retrieved_docs", []))
            summary = f"retrieve_knowledge docs={len(retrieved_docs)} query={retrieval_result.get('rewritten_query', '')}"
            return {
                "intent": "qa",
                "route_target": "qa",
                "requires_retrieval": False,
                "knowledge_scope": retrieval_state["knowledge_scope"],
                "tool_intent": TOOL_INTENT_NONE,
                "rewritten_query": retrieval_result.get("rewritten_query"),
                "retrieved_docs": retrieved_docs,
                "executor_observations": self._append_observation(
                    state,
                    kind=action,
                    summary=summary,
                    payload={
                        "rewritten_query": retrieval_result.get("rewritten_query"),
                        "doc_count": len(retrieved_docs),
                    },
                ),
                "planning_completed": False,
                "agent_name": "executor",
            }

        if action == PLANNER_ACTION_CALL_DATETIME:
            # 时间类工具直接走 QAAgent 的 datetime 分支生成最终话术，
            # 不再返回 planner 做二次规划。
            qa_state = dict(state)
            qa_state["tool_intent"] = TOOL_INTENT_DATETIME
            qa_state["requires_retrieval"] = False
            result = await self.qa_agent.run(qa_state)
            return {
                **result,
                "intent": "qa",
                "route_target": "qa",
                "requires_retrieval": False,
                "tool_intent": TOOL_INTENT_DATETIME,
                "executor_observations": self._append_observation(
                    state,
                    kind=action,
                    summary=str(result.get("agent_output", "")),
                    payload={"tool_name": "current_datetime"},
                ),
                "planning_completed": True,
            }

        if action == PLANNER_ACTION_RECALL_MEMORY:
            # 记忆召回同理：executor 负责触发 QA 的 recall 分支，
            # QA 读记忆并输出最终回答。
            qa_state = dict(state)
            qa_state["tool_intent"] = TOOL_INTENT_MEMORY_RECALL
            qa_state["requires_retrieval"] = False
            result = await self.qa_agent.run(qa_state)
            return {
                **result,
                "intent": "qa",
                "route_target": "qa",
                "requires_retrieval": False,
                "tool_intent": TOOL_INTENT_MEMORY_RECALL,
                "executor_observations": self._append_observation(
                    state,
                    kind=action,
                    summary=str(result.get("agent_output", "")),
                    payload={"tool_name": "memory_recall"},
                ),
                "planning_completed": True,
            }

        if action == PLANNER_ACTION_CALL_WEB_SEARCH:
            # web_search 先只拿搜索 observation，不在 executor 里直接组织最终自然语言，
            # 这样可以让 planner 统一看到搜索结果，再决定 handoff 给 QA 整合回答。
            search_state = dict(state)
            search_state["tool_intent"] = TOOL_INTENT_WEB_SEARCH
            search_state["requires_retrieval"] = False
            search_state["rewritten_query"] = str(
                args.get("query") or state.get("rewritten_query") or state.get("user_input") or ""
            )
            web_search_only = getattr(self.qa_agent, "web_search_only", None)
            if web_search_only is None:
                raise RuntimeError("qa agent does not implement web_search_only")
            result = await web_search_only(search_state)
            tool_outputs = dict(result.get("tool_outputs", {}))
            tool_payload = dict(tool_outputs.get("google_search") or {})
            organic_results = list(tool_payload.get("organic_results") or [])
            summary = (
                f"call_web_search hits={len(organic_results)} query="
                f"{result.get('rewritten_query', search_state['rewritten_query'])}"
            )
            return {
                "intent": "qa",
                "route_target": "qa",
                "requires_retrieval": False,
                "tool_intent": TOOL_INTENT_WEB_SEARCH,
                "rewritten_query": result.get("rewritten_query", search_state["rewritten_query"]),
                "tools_used": list(result.get("tools_used", [])),
                "tool_outputs": tool_outputs,
                "executor_observations": self._append_observation(
                    state,
                    kind=action,
                    summary=summary,
                    payload={
                        "tool_name": "google_search",
                        "query": result.get("rewritten_query", search_state["rewritten_query"]),
                        "organic_result_count": len(organic_results),
                    },
                ),
                "planning_completed": False,
                "agent_name": "executor",
            }

        # 未知动作只记录 observation，不让图直接报错中断。
        return {
            "planning_completed": False,
            "executor_observations": self._append_observation(
                state,
                kind="executor_unknown_action",
                summary=f"unknown planner action: {action}",
                payload={"planner_action_args": args},
            ),
            "agent_name": "executor",
        }

    async def planner_node(self, state: LiveAgentState):
        # Skill 前置拦截：命中则直接返回，跳过 Router LLM
        if self.skill_registry is not None:
            user_input = state.get("user_input", "")
            matched = self.skill_registry.match(user_input)
            if matched:
                logger.info("[PLANNER] skill intercepted: %s", matched.id)
                return {
                    "agent_output": matched.response.text,
                    "planning_completed": True,
                    "intent": matched.response.intent,
                    "agent_name": matched.response.agent_name,
                    "route_reason": f"skill_intercept:{matched.id}",
                }
        # 优先使用轻量路由接口（直接返回节点名称）
        try:
            return await self.router_agent.route(state)
        except Exception as exc:
            # 回退：如果路由失败，默认路由到 qa，避免图卡死
            logger.warning("[PLANNER] route failed, using fallback: %s", exc)
            return {
                "route_target": "qa",
                "route_reason": "route_failed_fallback",
                "intent": "qa",
                "route_low_confidence": True,
                "agent_name": "router",
            }

    async def executor_node(self, state: LiveAgentState):
        # executor 只执行 planner 给出的结构化动作，不自行做业务判断。
        return await self._run_node("executor", state, self._execute_planner_action, category="graph_node")

    async def qa_node(self, state: LiveAgentState):
        # qa 节点负责知识检索问答、记忆问答、web 搜索整合等最终回答生成。
        return await self._run_node("qa", state, self.qa_agent.run, category="graph_node")

    async def direct_node(self, state: LiveAgentState):
        # direct 节点处理无需检索的直接回复类问题。
        return await self._run_node("direct", state, self.direct_agent.run, category="graph_node")

    async def script_node(self, state: LiveAgentState):
        # script 节点处理脚本生成类请求。
        return await self._run_node("script", state, self.script_agent.run, category="graph_node")

    async def analyst_node(self, state: LiveAgentState):
        # analyst 节点处理复盘/分析类请求。
        return await self._run_node("analyst", state, self.analyst_agent.run, category="graph_node")

    async def guardrail_node(self, state: LiveAgentState):
        # 所有产出的最终内容统一进入 guardrail，
        # 在这里做权限、敏感词、夸大宣传、长度、引用合法性等治理。
        result = await self._run_node(
            "guardrail",
            state,
            self.guardrail_service.evaluate,
            category="graph_node",
        )
        return {
            "guardrail_pass": result.passed,
            "guardrail_reason": result.reason,
            "guardrail_action": result.action,
            "guardrail_violations": result.violations,
            "final_output": result.final_output,
            "references": result.references if result.references is not None else state.get("references", []),
            "agent_name": state.get("agent_name", "guardrail"),
        }

    async def ainvoke(self, state: dict):
        # 外部统一从这里进入主图。
        return await self.graph.ainvoke(state)
