from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    return trace_id_var.get()


class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        trace_id_var.set(trace_id)
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response
