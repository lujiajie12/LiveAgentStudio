from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.config import settings


F = TypeVar("F", bound=Callable[..., Any])


try:  # pragma: no cover - optional dependency
    from langsmith import traceable as _langsmith_traceable
except ImportError:  # pragma: no cover
    _langsmith_traceable = None


def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F] | F:
    """Use LangSmith tracing when installed, otherwise leave functions untouched."""
    if _langsmith_traceable is None:
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func: F) -> F:
            return func

        return decorator
    return _langsmith_traceable(*args, **kwargs)


def configure_langsmith_environment() -> None:
    """Expose backend/.env LangSmith settings to LangChain/LangGraph runtime."""
    if not (settings.LANGSMITH_TRACING or settings.LANGSMITH_TRACING_V2):
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    # Keep compatibility variables for LangChain/LangSmith versions used in this stack.
    os.environ.setdefault("LANGSMITH_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

    _set_env_if_present("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    _set_env_if_present("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
    _set_env_if_present("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ.setdefault(
        "LANGCHAIN_CALLBACKS_BACKGROUND",
        "true" if settings.LANGCHAIN_CALLBACKS_BACKGROUND else "false",
    )


def build_langsmith_config(
    state: dict[str, Any],
    *,
    run_name: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    base_tags = [
        item.strip()
        for item in str(settings.LANGSMITH_RUN_TAGS_STR or "").split(",")
        if item.strip()
    ]
    metadata = summarize_state_for_langsmith(state)
    metadata["project_name"] = settings.PROJECT_NAME
    return {
        "run_name": run_name,
        "tags": [*base_tags, *(tags or [])],
        "metadata": metadata,
    }


def summarize_state_for_langsmith(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": _string_or_none(state.get("trace_id")),
        "run_id": _string_or_none(state.get("run_id")),
        "session_id": _string_or_none(state.get("session_id")),
        "user_id": _string_or_none(state.get("user_id")),
        "app_id": _string_or_none(state.get("app_id")),
        "live_stage": _string_or_none(state.get("live_stage")),
        "current_product_id": _string_or_none(state.get("current_product_id")),
        "intent": _string_or_none(state.get("intent")),
        "route_target": _string_or_none(state.get("route_target")),
        "planner_action": _string_or_none(state.get("planner_action")),
        "tool_intent": _string_or_none(state.get("tool_intent")),
        "agent_name": _string_or_none(state.get("agent_name")),
        "memory_status": _string_or_none(state.get("memory_status")),
        "short_term_memory_turns": len(state.get("short_term_memory") or []),
        "long_term_memory_hits": int(state.get("long_term_memory_hits") or 0),
    }


def summarize_graph_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("state")
    if not isinstance(state, dict):
        state = {}
    return {
        "state": {
            **summarize_state_for_langsmith(state),
            "user_input_preview": _preview(state.get("user_input")),
        }
    }


def summarize_graph_outputs(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {"output_preview": _preview(output)}
    return {
        **summarize_state_for_langsmith(output),
        "guardrail_pass": output.get("guardrail_pass"),
        "guardrail_action": _string_or_none(output.get("guardrail_action")),
        "qa_confidence": output.get("qa_confidence"),
        "unresolved": output.get("unresolved"),
        "references_count": len(output.get("references") or []),
        "retrieved_docs_count": len(output.get("retrieved_docs") or []),
        "final_output_preview": _preview(output.get("final_output") or output.get("agent_output")),
    }


def summarize_memory_search_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("state")
    if not isinstance(state, dict):
        state = {}
    return {
        "state": {
            **summarize_state_for_langsmith(state),
            "query_preview": _preview(state.get("user_input")),
        }
    }


def summarize_memory_write_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    metadata = inputs.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "user_id": _string_or_none(inputs.get("user_id")),
        "run_id": _string_or_none(inputs.get("run_id")),
        "current_product_id": _string_or_none(inputs.get("current_product_id")),
        "user_input_preview": _preview(inputs.get("user_input")),
        "assistant_output_preview": _preview(inputs.get("assistant_output")),
        "metadata": {
            "route_target": _string_or_none(metadata.get("route_target")),
            "tool_intent": _string_or_none(metadata.get("tool_intent")),
            "agent_name": _string_or_none(metadata.get("agent_name")),
            "qa_confidence": metadata.get("qa_confidence"),
            "long_term_memory_hits": metadata.get("long_term_memory_hits"),
        },
    }


def summarize_memory_records(output: Any) -> dict[str, Any]:
    records = output if isinstance(output, list) else []
    return {
        "count": len(records),
        "records": [
            {
                "memory_id": _string_or_none(getattr(item, "memory_id", "")),
                "score": getattr(item, "score", 0.0),
                "memory_types": list((getattr(item, "metadata", {}) or {}).get("memory_types") or []),
                "summary_preview": _preview((getattr(item, "metadata", {}) or {}).get("memory_summary")),
            }
            for item in records[:5]
        ],
    }


def summarize_memory_write_output(output: Any) -> dict[str, Any]:
    return {"stored": bool(output)}


def _set_env_if_present(name: str, value: Any) -> None:
    text = str(value or "").strip()
    if text:
        os.environ.setdefault(name, text)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _preview(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
