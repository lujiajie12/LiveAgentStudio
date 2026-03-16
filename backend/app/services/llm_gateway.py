import json
from typing import Any

from app.core.config import settings

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None


class LLMGateway:
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class OpenAILLMGateway(LLMGateway):
    def __init__(self):
        self._client = None
        if settings.OPENAI_API_KEY and ChatOpenAI is not None:
            self._client = ChatOpenAI(
                model=settings.ROUTER_MODEL,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                timeout=settings.ROUTER_TIMEOUT_MS / 1000,
                temperature=0,
            )

    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self._client is None:
            return self._heuristic_response(user_prompt)

        response = await self._client.ainvoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        return json.loads(response.content)

    def _heuristic_response(self, user_prompt: str) -> dict[str, Any]:
        try:
            payload = json.loads(user_prompt)
            lowered = str(payload.get("user_input", "")).lower()
        except json.JSONDecodeError:
            lowered = user_prompt.lower()
        if any(keyword in lowered for keyword in ["卖点", "促单", "话术", "库存"]):
            intent = "script"
        elif any(keyword in lowered for keyword in ["复盘", "统计", "高频", "report"]):
            intent = "analyst"
        elif any(keyword in lowered for keyword in ["你好", "天气", "random", "乱码"]):
            intent = "unknown"
        else:
            intent = "qa"
        return {
            "intent": intent,
            "confidence": 0.72 if intent != "unknown" else 0.55,
            "reason": "heuristic_fallback",
        }
