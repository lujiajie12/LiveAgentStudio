from abc import ABC, abstractmethod

from app.graph.state import LiveAgentState, StatePatch


class BaseAgent(ABC):
    name: str

    @abstractmethod
    async def run(self, state: LiveAgentState) -> StatePatch:
        raise NotImplementedError
