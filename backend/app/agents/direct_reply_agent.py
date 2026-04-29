import json
import re
from typing import Protocol

from app.agents.base import BaseAgent
from app.core.logging import get_logger
from app.graph.state import LiveAgentState, StatePatch

logger = get_logger(__name__)


class DirectReplyLLM(Protocol):
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        ...


DIRECT_AGENT_PROFILE = (
    "\u6211\u662f LiveAgent \u76f4\u64ad\u4e2d\u53f0\u667a\u80fd\u52a9\u624b\uff0c\u9762\u5411\u76f4\u64ad\u7535\u5546\u573a\u666f\u7684\u591a\u667a\u80fd\u4f53\u7cfb\u7edf\u3002\n"
    "\u6211\u7684\u670d\u52a1\u80fd\u529b\uff1a\n"
    "- \u5546\u54c1\u8d44\u6599\u95ee\u7b54\uff1a\u56de\u7b54\u5546\u54c1\u53c2\u6570\u3001\u6750\u8d28\u3001\u578b\u53f7\u3001\u9002\u7528\u4eba\u7fa4\u3001\u7269\u6d41\u3001\u552e\u540e\u548c\u89c4\u5219\u95ee\u9898\n"
    "- \u5bf9\u8bdd\u8bb0\u5fc6\u56de\u6eaf\uff1a\u56de\u987e\u521a\u521a\u95ee\u8fc7\u7684\u95ee\u9898\u548c\u8fd1\u671f\u5bf9\u8bdd\u5185\u5bb9\n"
    "- \u5b9e\u65f6\u4fe1\u606f\u67e5\u8be2\uff1a\u83b7\u53d6\u65e5\u671f\u65f6\u95f4\u3001\u91d1\u4ef7\u3001\u65b0\u95fb\u7b49\u5b9e\u65f6\u4fe1\u606f\n"
    "- \u8bdd\u672f\u4e0e\u6587\u6848\u751f\u6210\uff1a\u751f\u6210\u53e3\u64ad\u3001\u4fc3\u5355\u6587\u6848\u548c\u76f4\u64ad\u811a\u672c\n"
    "- \u6570\u636e\u590d\u76d8\u5206\u6790\uff1a\u5728\u6388\u6743\u573a\u666f\u4e0b\u8f93\u51fa\u7edf\u8ba1\u3001\u5206\u6790\u548c\u590d\u76d8\u5185\u5bb9\n"
    "\u6211\u7684\u9650\u5236\uff1a\u4e0d\u7f16\u9020\u5546\u54c1\u4e8b\u5b9e\uff0c\u9700\u8981\u8d44\u6599\u652f\u6491\u65f6\u4ea4\u7ed9\u77e5\u8bc6\u5e93\u5904\u7406\uff0c\u4e0d\u4e3b\u52a8\u5939\u5e26\u5546\u54c1\u6216\u4fc3\u9500\u4fe1\u606f\u3002"
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_provider_unavailable_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(token in message for token in ("arrearage", "access denied", "overdue-payment", "insufficient_quota"))


def _provider_unavailable_reply() -> str:
    return (
        "\u5f53\u524d\u5927\u6a21\u578b\u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528\uff0c\u672a\u80fd\u6b63\u5e38\u751f\u6210\u56de\u7b54\u3002\n\n"
        "\u5df2\u5b9a\u4f4d\u5230\u4e0a\u6e38\u6a21\u578b\u670d\u52a1\u8fd4\u56de\u9519\u8bef\uff0c\u8bf7\u68c0\u67e5\u6a21\u578b\u4f9b\u5e94\u5546\u8d26\u53f7\u72b6\u6001\u6216\u989d\u5ea6\u914d\u7f6e\u540e\u518d\u8bd5\u3002\n"
        "\u5982\u679c\u4f60\u73b0\u5728\u662f\u5728\u4f7f\u7528 DashScope/Qwen \u517c\u5bb9\u63a5\u53e3\uff0c\u5f53\u524d\u65e5\u5fd7\u663e\u793a\u662f\u8d26\u6237\u6b20\u8d39\uff08Arrearage\uff09\u5bfc\u81f4\u8c03\u7528\u5931\u8d25\u3002"
    )


def _looks_like_noise_input(query: str) -> bool:
    compact = query.strip()
    if not compact:
        return True
    if re.fullmatch(r"[0-9\s]+", compact):
        return True
    if re.fullmatch(r"[0-9A-Za-z\W_]{1,3}", compact):
        return True
    if re.fullmatch(r"(.)\1{2,}", compact):
        return True
    return False


class DirectReplyAgent(BaseAgent):
    name = "direct"

    def __init__(self, llm_client: DirectReplyLLM | None = None):
        self.llm_client = llm_client

    def _fallback_reply(self, state: LiveAgentState, reason: str = "unknown") -> str:
        query = _normalize_text(state.get("user_input", ""))
        logger.warning(
            "direct_reply_fallback trace_id=%s reason=%s query=%s route_target=%s planner_mode=%s route_fallback_reason=%s",
            state.get("trace_id"),
            reason,
            query,
            state.get("route_target"),
            state.get("planner_mode"),
            state.get("route_fallback_reason"),
        )
        if _looks_like_noise_input(query):
            return "\u8fd9\u4e2a\u8f93\u5165\u8fd8\u4e0d\u591f\u660e\u786e\u3002\u4f60\u53ef\u4ee5\u76f4\u63a5\u544a\u8bc9\u6211\u4f60\u7684\u95ee\u9898\uff0c\u4f8b\u5982\u7cfb\u7edf\u80fd\u505a\u4ec0\u4e48\uff0c\u6216\u8005\u67d0\u4e2a\u5546\u54c1\u7684\u5177\u4f53\u4fe1\u606f\u3002"
        return (
            "\u60a8\u597d\uff01\n\n"
            "\u6211\u662f LiveAgent \u76f4\u64ad\u4e2d\u53f0\u667a\u80fd\u52a9\u624b\uff0c\u8d1f\u8d23\u5904\u7406\u7b80\u5355\u76f4\u7b54\u3001\u7cfb\u7edf\u8bf4\u660e\u4ee5\u53ca\u76f4\u64ad\u573a\u666f\u4e0b\u7684\u591a\u80fd\u529b\u534f\u540c\u3002\n\n"
            "\u6211\u53ef\u4ee5\u4e3a\u60a8\u63d0\u4f9b\u4ee5\u4e0b\u670d\u52a1\uff1a\n"
            "- \u5546\u54c1\u8d44\u6599\u95ee\u7b54\uff1a\u56de\u7b54\u53c2\u6570\u3001\u6750\u8d28\u3001\u578b\u53f7\u3001\u9002\u7528\u4eba\u7fa4\u3001\u7269\u6d41\u548c\u552e\u540e\u95ee\u9898\n"
            "- \u5bf9\u8bdd\u8bb0\u5fc6\u56de\u6eaf\uff1a\u56de\u987e\u60a8\u521a\u521a\u63d0\u8fc7\u7684\u95ee\u9898\u548c\u4e4b\u524d\u7684\u5bf9\u8bdd\u5185\u5bb9\n"
            "- \u5b9e\u65f6\u4fe1\u606f\u67e5\u8be2\uff1a\u5728\u9700\u8981\u65f6\u83b7\u53d6\u65e5\u671f\u65f6\u95f4\u3001\u91d1\u4ef7\u3001\u65b0\u95fb\u7b49\u5b9e\u65f6\u4fe1\u606f\n"
            "- \u8bdd\u672f\u4e0e\u6587\u6848\u751f\u6210\uff1a\u751f\u6210\u53e3\u64ad\u3001\u4fc3\u5355\u6587\u6848\u548c\u76f4\u64ad\u811a\u672c\n"
            "- \u6570\u636e\u590d\u76d8\u5206\u6790\uff1a\u5728\u6388\u6743\u573a\u666f\u4e0b\u8f93\u51fa\u7edf\u8ba1\u3001\u5206\u6790\u548c\u590d\u76d8\u5185\u5bb9\n\n"
            "\u5982\u679c\u60a8\u544a\u8bc9\u6211\u5177\u4f53\u95ee\u9898\uff0c\u6211\u4f1a\u81ea\u52a8\u9009\u62e9\u66f4\u5408\u9002\u7684\u5904\u7406\u65b9\u5f0f\u3002"
        )

    # PLACEHOLDER_RUN_METHOD

    async def run(self, state: LiveAgentState) -> StatePatch:
        query = _normalize_text(state.get("user_input", ""))

        if self.llm_client is None:
            logger.error(
                "direct_reply_llm_unavailable trace_id=%s query=%s llm_client_configured=%s",
                state.get("trace_id"),
                query,
                False,
            )
            answer = self._fallback_reply(state, reason="llm_client_not_configured")
            return {
                "agent_output": answer,
                "references": [],
                "retrieved_docs": [],
                "qa_confidence": 0.75,
                "unresolved": False,
                "agent_name": self.name,
            }

        system_prompt = (
            "\u4f60\u662f\u76f4\u64ad\u7535\u5546\u591a\u667a\u80fd\u4f53\u7cfb\u7edf\u4e2d\u7684\u76f4\u63a5\u56de\u590d\u667a\u80fd\u4f53\u3002\n\n"
            "\u3010\u4f60\u7684\u8eab\u4efd\u3011\n"
            f"{DIRECT_AGENT_PROFILE}\n\n"
            "\u3010\u53ef\u76f4\u63a5\u56de\u7b54\u3011\n"
            "\u95ee\u5019\u5bd2\u6684\u3001\u8eab\u4efd\u4ecb\u7ecd\u3001\u80fd\u529b\u8bf4\u660e\u3001\u7b80\u5355\u6f84\u6e05\u3001\u6280\u672f\u6027\u95ee\u9898\uff08\u5982\u5e95\u5c42\u6a21\u578b\uff09\u3002\n"
            "\u5982\u679c\u7528\u6237\u95ee\u201c\u4f60\u662f\u4ec0\u4e48 agent\u201d\u3001\u201c\u4f60\u662f\u4ec0\u4e48\u52a9\u624b\u201d\u4e4b\u7c7b\u7684\u8eab\u4efd\u95ee\u9898\uff0c"
            "\u4f18\u5148\u6309 LiveAgent \u7cfb\u7edf\u5185\u7684\u89d2\u8272\u8eab\u4efd\u56de\u7b54\uff0c\u660e\u786e\u8bf4\u660e\u8fd9\u662f\u4ea7\u54c1\u5185\u7684 agent \u5b9a\u4f4d\uff0c"
            "\u4e0d\u662f\u5728\u95ee\u5e95\u5c42\u6a21\u578b\u5382\u5546\u3001\u53c2\u6570\u89c4\u6a21\u6216\u6a21\u578b\u67b6\u6784\u3002\n"
            "\u56de\u7b54\u8eab\u4efd\u95ee\u9898\u65f6\u53c2\u8003\u4e0a\u65b9\u8eab\u4efd\u63cf\u8ff0\uff1b\u56de\u7b54\u6280\u672f\u6027\u95ee\u9898\u65f6\u53ef\u7ed3\u5408\u81ea\u8eab\u77e5\u8bc6\u5982\u5b9e\u4f5c\u7b54\u3002\n\n"
            "\u3010\u7981\u6b62\u7f16\u9020\u3011\n"
            "\u5177\u4f53\u5546\u54c1\u4fe1\u606f\u3001\u4ef7\u683c\u3001\u5e93\u5b58\u3001\u4f18\u60e0\u3001\u552e\u540e\u3001\u7269\u6d41\u7b49\u9700\u8981\u77e5\u8bc6\u5e93\u652f\u6491\u7684\u5185\u5bb9\u3002\n"
            "\u4e0d\u786e\u5b9a\u65f6\u5f15\u5bfc\u7528\u6237\u63d0\u95ee\u4ee5\u89e6\u53d1\u77e5\u8bc6\u5e93\u68c0\u7d22\u3002\n\n"
            "\u3010\u56de\u7b54\u98ce\u683c\u3011\n"
            "\u81ea\u7136\u3001\u4e13\u4e1a\u3001\u7b80\u6d01\u7684\u4e2d\u6587\u3002\u95ee\u4ec0\u4e48\u7b54\u4ec0\u4e48\uff0c\u4e0d\u8fc7\u5ea6\u5c55\u5f00\u3002\n"
            "\u95ee\u5019\u53ea\u9700\u7b80\u77ed\u56de\u5e94\uff1b\u95ee\u5355\u4e2a\u80fd\u529b\u53ea\u7b54\u8be5\u80fd\u529b\uff1b\u95ee\u8eab\u4efd\u518d\u505a\u5b8c\u6574\u4ecb\u7ecd\u3002\n"
            "\u4e0d\u4e3b\u52a8\u63d0\u53ca\u5546\u54c1\u3001SKU\u3001\u4ef7\u683c\u3001\u6d3b\u52a8\u7b49\u4e1a\u52a1\u4fe1\u606f\uff0c\u9664\u975e\u7528\u6237\u660e\u786e\u8be2\u95ee\u3002\n"
        )
        # PLACEHOLDER_USER_PROMPT
        user_prompt = json.dumps(
            {
                "user_input": query,
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
                "short_term_memory": list(state.get("short_term_memory", []))[-4:],
            },
            ensure_ascii=False,
        )

        try:
            answer = (await self.llm_client.ainvoke_text(system_prompt, user_prompt)).strip()
            logger.info(
                "direct_reply_llm_success trace_id=%s query=%s answer_preview=%s",
                state.get("trace_id"),
                query,
                answer[:120],
            )
        except Exception as exc:
            logger.exception(
                "direct_reply_llm_failed trace_id=%s query=%s error=%s",
                state.get("trace_id"),
                query,
                exc,
            )
            if _is_provider_unavailable_error(exc):
                answer = _provider_unavailable_reply()
            else:
                answer = self._fallback_reply(state, reason="llm_invoke_failed")

        if not answer:
            logger.warning(
                "direct_reply_llm_empty trace_id=%s query=%s",
                state.get("trace_id"),
                query,
            )
            answer = self._fallback_reply(state, reason="llm_empty_response")

        return {
            "agent_output": answer,
            "references": [],
            "retrieved_docs": [],
            "qa_confidence": 0.85,
            "unresolved": False,
            "agent_name": self.name,
        }
