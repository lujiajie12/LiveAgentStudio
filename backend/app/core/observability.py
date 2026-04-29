from __future__ import annotations

import contextlib
from contextvars import ContextVar
from time import perf_counter
from typing import Any, Iterator

from app.core.trace import get_trace_id
from app.schemas.domain import ToolCallLogRecord


session_id_var: ContextVar[str] = ContextVar("session_id", default="")
tool_repo_var: ContextVar[Any] = ContextVar("tool_repo", default=None)


@contextlib.contextmanager
def bind_observability(session_id: str, tool_log_repository: Any) -> Iterator[None]:
    session_token = session_id_var.set(session_id)
    repo_token = tool_repo_var.set(tool_log_repository)
    try:
        yield
    finally:
        session_id_var.reset(session_token)
        tool_repo_var.reset(repo_token)


async def record_tool_call(
    tool_name: str,
    *,
    node_name: str | None = None,
    category: str = "misc",
    input_payload: dict[str, Any] | None = None,
    output_summary: str | None = None,
    latency_ms: int = 0,
    status: str = "ok",
    trace_id: str | None = None,
    session_id: str | None = None,
) -> None:
    repository = tool_repo_var.get()
    if repository is None:
        return
    try:
        await repository.create(
            ToolCallLogRecord(
                session_id=session_id or session_id_var.get() or None,
                trace_id=trace_id or get_trace_id() or None,
                tool_name=tool_name,
                node_name=node_name,
                category=category,
                input_payload=input_payload or {},
                output_summary=output_summary,
                latency_ms=latency_ms,
                status=status,
            )
        )
    except Exception:
        return


async def record_timed_tool_call(
    tool_name: str,
    *,
    started_at: float,
    node_name: str | None = None,
    category: str = "misc",
    input_payload: dict[str, Any] | None = None,
    output_summary: str | None = None,
    status: str = "ok",
) -> None:
    await record_tool_call(
        tool_name,
        node_name=node_name,
        category=category,
        input_payload=input_payload,
        output_summary=output_summary,
        latency_ms=int((perf_counter() - started_at) * 1000),
        status=status,
    )
