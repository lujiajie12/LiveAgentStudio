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
    PLANNER_ACTION_HANDOFF_AGENT,
    PLANNER_ACTION_RECALL_MEMORY,
    PLANNER_ACTION_RETRIEVE_KNOWLEDGE,
    PLANNER_TOOL_ACTIONS,
    TOOL_INTENT_DATETIME,
    TOOL_INTENT_MEMORY_RECALL,
    TOOL_INTENT_NONE,
    TOOL_INTENT_WEB_SEARCH,
    RouterAgent,
)
from app.core.observability import record_tool_call, record_timed_tool_call
from app.graph.state import LiveAgentState
from app.services.guardrail_service import GuardrailService


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
    ):
        self.router_agent = router_agent
        self.guardrail_service = guardrail_service
        self.qa_agent: BaseAgent = qa_agent or QAAgent(retrieval_pipeline=retrieval_pipeline)
        self.direct_agent: BaseAgent = direct_agent or DirectReplyAgent()
        self.script_agent: BaseAgent = script_agent or ScriptPlaceholderAgent(retrieval_pipeline=retrieval_pipeline)
        self.analyst_agent: BaseAgent = analyst_agent or AnalystPlaceholderAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
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
        planner_action = str(state.get("planner_action") or "").strip()
        if planner_action in PLANNER_TOOL_ACTIONS:
            return "executor"
        route_target = state.get("route_target")
        if route_target in {"qa", "direct", "script", "analyst"}:
            return route_target
        if state.get("planning_completed") or state.get("agent_output"):
            return "guardrail"
        return "qa"

    def next_after_executor(self, state: LiveAgentState) -> str:
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
        action = str(state.get("planner_action") or "").strip()
        args = dict(state.get("planner_action_args") or {})

        if action == PLANNER_ACTION_RETRIEVE_KNOWLEDGE:
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
        return await self._run_node("planner", state, self.router_agent.run, category="graph_node")

    async def executor_node(self, state: LiveAgentState):
        return await self._run_node("executor", state, self._execute_planner_action, category="graph_node")

    async def qa_node(self, state: LiveAgentState):
        return await self._run_node("qa", state, self.qa_agent.run, category="graph_node")

    async def direct_node(self, state: LiveAgentState):
        return await self._run_node("direct", state, self.direct_agent.run, category="graph_node")

    async def script_node(self, state: LiveAgentState):
        return await self._run_node("script", state, self.script_agent.run, category="graph_node")

    async def analyst_node(self, state: LiveAgentState):
        return await self._run_node("analyst", state, self.analyst_agent.run, category="graph_node")

    async def guardrail_node(self, state: LiveAgentState):
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
        return await self.graph.ainvoke(state)
