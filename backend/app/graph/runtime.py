from time import perf_counter
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.agents.placeholders import AnalystPlaceholderAgent, ScriptPlaceholderAgent
from app.agents.qa_agent import QAAgent
from app.agents.router import RouterAgent
from app.core.observability import record_tool_call, record_timed_tool_call
from app.graph.state import LiveAgentState
from app.services.guardrail_service import GuardrailService


class GraphRuntime:
    # 初始化 LangGraph 运行时，并注入路由、业务智能体和治理节点。
    def __init__(
        self,
        router_agent: RouterAgent,
        guardrail_service: GuardrailService,
        retrieval_pipeline=None,
        qa_agent: BaseAgent | None = None,
        script_agent: BaseAgent | None = None,
        analyst_agent: BaseAgent | None = None,
    ):
        self.router_agent = router_agent
        self.guardrail_service = guardrail_service
        self.qa_agent: BaseAgent = qa_agent or QAAgent(retrieval_pipeline=retrieval_pipeline)
        self.script_agent: BaseAgent = script_agent or ScriptPlaceholderAgent(retrieval_pipeline=retrieval_pipeline)
        self.analyst_agent: BaseAgent = analyst_agent or AnalystPlaceholderAgent()
        self.graph = self._build_graph()

    # 构建状态图主链：Router -> 业务 Agent -> Guardrail。
    def _build_graph(self):
        workflow = StateGraph(LiveAgentState)
        workflow.add_node("router", self.router_node)
        workflow.add_node("qa", self.qa_node)
        workflow.add_node("script", self.script_node)
        workflow.add_node("analyst", self.analyst_node)
        workflow.add_node("guardrail", self.guardrail_node)

        workflow.add_edge(START, "router")
        workflow.add_conditional_edges(
            "router",
            self.route_next,
            {
                "qa": "qa",
                "script": "script",
                "analyst": "analyst",
                "unknown": "qa",
            },
        )
        workflow.add_edge("qa", "guardrail")
        workflow.add_edge("script", "guardrail")
        workflow.add_edge("analyst", "guardrail")
        workflow.add_edge("guardrail", END)
        return workflow.compile()

    # 根据 Router 写入的 intent 决定下一跳业务节点。
    def route_next(self, state: LiveAgentState) -> str:
        return state.get("intent", "qa")

    # 统一包裹节点执行过程，记录进入/退出日志与节点耗时。
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

    # 把不同节点的返回结果统一压缩成可写入日志的摘要文本。
    def _summarize_result(self, result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("agent_output") or result.get("final_output") or "")[:200]
        final_output = getattr(result, "final_output", "")
        if final_output:
            return str(final_output)[:200]
        return str(result)[:200]

    # 执行路由节点。
    async def router_node(self, state: LiveAgentState):
        return await self._run_node("router", state, self.router_agent.run, category="graph_node")

    # 执行 QA 节点。
    async def qa_node(self, state: LiveAgentState):
        return await self._run_node("qa", state, self.qa_agent.run, category="graph_node")

    # 执行 Script 节点。
    async def script_node(self, state: LiveAgentState):
        return await self._run_node("script", state, self.script_agent.run, category="graph_node")

    # 执行 Analyst 节点。
    async def analyst_node(self, state: LiveAgentState):
        return await self._run_node("analyst", state, self.analyst_agent.run, category="graph_node")

    # 对业务输出做统一治理，并把治理结果回填到状态中。
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

    # 对外暴露统一的异步图调用入口。
    async def ainvoke(self, state: dict):
        return await self.graph.ainvoke(state)
