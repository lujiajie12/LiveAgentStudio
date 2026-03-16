from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.agents.placeholders import (
    AnalystPlaceholderAgent,
    QAPlaceholderAgent,
    ScriptPlaceholderAgent,
)
from app.agents.router import RouterAgent
from app.graph.state import LiveAgentState
from app.services.guardrail_service import GuardrailService


class GraphRuntime:
    def __init__(self, router_agent: RouterAgent, guardrail_service: GuardrailService):
        self.router_agent = router_agent
        self.guardrail_service = guardrail_service
        self.qa_agent: BaseAgent = QAPlaceholderAgent()
        self.script_agent: BaseAgent = ScriptPlaceholderAgent()
        self.analyst_agent: BaseAgent = AnalystPlaceholderAgent()
        self.graph = self._build_graph()

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

    def route_next(self, state: LiveAgentState) -> str:
        return state.get("intent", "qa")

    async def router_node(self, state: LiveAgentState):
        return await self.router_agent.run(state)

    async def qa_node(self, state: LiveAgentState):
        return await self.qa_agent.run(state)

    async def script_node(self, state: LiveAgentState):
        return await self.script_agent.run(state)

    async def analyst_node(self, state: LiveAgentState):
        return await self.analyst_agent.run(state)

    async def guardrail_node(self, state: LiveAgentState):
        result = await self.guardrail_service.evaluate(state.get("agent_output", ""))
        return {
            "guardrail_pass": result.passed,
            "guardrail_reason": result.reason,
            "final_output": result.final_output,
            "agent_name": state.get("agent_name", "guardrail"),
        }

    async def ainvoke(self, state: dict):
        return await self.graph.ainvoke(state)
