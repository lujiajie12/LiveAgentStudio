from app.agents.base import BaseAgent
from app.graph.state import LiveAgentState, StatePatch


class QAPlaceholderAgent(BaseAgent):
    name = "qa"

    async def run(self, state: LiveAgentState) -> StatePatch:
        return {
            "agent_output": (
                f"这是 QA Agent 占位回复：已收到问题“{state['user_input']}”，"
                "后续会接入检索增强问答链路。"
            ),
            "references": [],
            "retrieved_docs": [],
            "agent_name": self.name,
        }


class ScriptPlaceholderAgent(BaseAgent):
    name = "script"

    async def run(self, state: LiveAgentState) -> StatePatch:
        return {
            "agent_output": (
                "这是 Script Agent 占位回复：建议突出商品卖点、价格锚点和互动口令。"
            ),
            "references": [],
            "retrieved_docs": [],
            "agent_name": self.name,
        }


class AnalystPlaceholderAgent(BaseAgent):
    name = "analyst"

    async def run(self, state: LiveAgentState) -> StatePatch:
        return {
            "agent_output": (
                "这是 Analyst Agent 占位回复：复盘能力将在后续版本接入报表和高频问题统计。"
            ),
            "references": [],
            "retrieved_docs": [],
            "agent_name": self.name,
        }
